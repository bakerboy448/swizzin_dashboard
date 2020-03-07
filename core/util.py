import sys
import os
from core.profiles import *
from flask import request, current_app
from flask_socketio import SocketIO, emit
import subprocess as sp
import json
import shutil
import datetime
from pwd import getpwnam
import psutil

try:
    from core.custom.profiles import *
except:
    pass

boottimestamp = os.stat("/proc").st_ctime
boottimeutc = datetime.datetime.fromtimestamp(boottimestamp).strftime('%b %d, %Y %H:%M:%S')

def str_to_class(str):
    return getattr(sys.modules[__name__], str)

def get_default_interface():
    """Get the default interface directly from /proc."""
    with open("/proc/net/route") as route:
        for line in route:
            fields = line.strip().split()
            if fields[1] != '00000000' or not int(fields[3], 16) & 2:
                continue
            return fields[0]

def generate_page_list(user):
    admin_user = current_app.config['ADMIN_USER']
    pages = []
    locks = os.listdir('/install')
    try:
        host = request.host.split(":")[0]
    except:
        host = request.host

    scheme = request.scheme
    for lock in locks:
        app = lock.split(".")[1]
        try:
            profile = str_to_class(app+"_meta")
        except:
            continue
        try:
            multiuser = profile.multiuser
        except:
            multiuser = False
        if multiuser == False and user != admin_user:
            continue
        try:
            scheme = profile.scheme
        except:
            scheme = request.scheme
        try:
            url = scheme+"://"+host+profile.baseurl
        except:
            url = False
        try:
            systemd = profile.systemd
        except:
            systemd = profile.name
        pages.append({"name": profile.name, "pretty_name": profile.pretty_name, "url": url, "systemd": systemd})
    return pages

def apps_status(username):
    apps = []
    admin_user = current_app.config['ADMIN_USER']
    locks = os.listdir('/install')
    ps = sp.Popen(('ps', 'axo', 'user:20,comm,cmd'), stdout=sp.PIPE).communicate()[0]
    procs = ps.splitlines()
    for lock in locks:
        application = lock.split(".")[1]
        try:
            profile = str_to_class(application+"_meta")
        except:
            continue
        try:
            multiuser = profile.multiuser
        except:
            multiuser = False
        if multiuser == False and username != admin_user:
            continue
        try:
            #If application is not run as user
            user = profile.runas
        except:
            user = username
        try:
            #If application in `ps` has another name
            application = profile.process
        except:
            application = profile.name
        try:
            systemd = profile.systemd
        except:
            systemd = profile.name
        if systemd == False:
            continue
        try:
            enabled = is_application_enabled(systemd, user)
        except:
            enabled = False
        
        status = is_process_running(procs, user, application)
        apps.append({"name": profile.name, "active": status, "enabled": enabled})
    return apps

def is_process_running(procs, username, application):
    result = False
    for p in procs:
        if username.lower() in str(p).lower():
            if application.lower() in str(p).lower():
                #print("True")
                result = True
                #print(result)
    return result

def is_application_enabled(application, user):
    if "@" in application:
        result = os.path.exists('/etc/systemd/system/multi-user.target.wants/{application}{user}.service'.format(application=application, user=user))
        #result = sp.run(('systemctl', 'is-enabled', application+user), stdout=sp.DEVNULL).returncode
    else:
        result = os.path.exists('/etc/systemd/system/multi-user.target.wants/{application}.service'.format(application=application))
        #result = sp.run(('systemctl', 'is-enabled', application), stdout=sp.DEVNULL).returncode
    #if result == 0:
    #    result = True
    #else:
    #    result = False
    return result

def systemctl(function, application):
    if function in ("enable", "disable"):
        result = sp.run(('sudo', 'systemctl', function, '--now', application), stdout=sp.DEVNULL).returncode
    else:
        result = sp.run(('sudo', 'systemctl', function, application), stdout=sp.DEVNULL).returncode
    return result

def vnstat_data(interface, mode):
    vnstat = sp.run(('vnstat', '-i', interface, '--json', mode), stdout=sp.PIPE)
    data = json.loads(vnstat.stdout.decode('utf-8'))
    #data = vnstat.stdout.decode('utf-8')
    return data

def vnstat_parse(interface, mode, query, position):
    result = vnstat_data(interface, mode)['interfaces'][0]['traffic'][query][position]
    result['rx'] = GetHumanReadableKB(result['rx'])
    result['tx'] = GetHumanReadableKB(result['tx'])
    return result

def disk_usage(location):
    total, used, free = shutil.disk_usage(location)
    totalh = GetHumanReadableB(total)
    usedh = GetHumanReadableB(used)
    freeh = GetHumanReadableB(free)
    usage = '{0:.2f}'.format((used / total * 100))
    return totalh, usedh, freeh, usage

def quota_usage(username):
    quota = sp.Popen(('quota', '-wpu', username), stdout=sp.PIPE)
    quota = quota.communicate()[0].decode("utf-8").split('\n')[2].split()
    fs = quota[0]
    used = quota[1]
    total = quota[2]
    free = total - used
    totalh = GetHumanReadableKB(total)
    usedh = GetHumanReadableKB(used)
    freeh = GetHumanReadableKB(free)
    usage = '{0:.2f}'.format((used / total * 100))
    return totalh, usedh, freeh, usage

def GetHumanReadableKB(size,precision=2):
    suffixes=['KB','MB','GB','TB','PB']
    suffixIndex = 0
    while size > 1024 and suffixIndex < 4:
        suffixIndex += 1 #increment the index of the suffix
        size = size/1024.0 #apply the division
    return "%.*f %s"%(precision,size,suffixes[suffixIndex])

def GetHumanReadableB(size,precision=2):
    suffixes=['B','KB','MB','GB','TB','PB']
    suffixIndex = 0
    while size > 1024 and suffixIndex < 4:
        suffixIndex += 1 #increment the index of the suffix
        size = size/1024.0 #apply the division
    return "%.*f %s"%(precision,size,suffixes[suffixIndex])

def get_nic_bytes(t, interface):
    with open('/sys/class/net/' + interface + '/statistics/' + t + '_bytes', 'r') as f:
        data = f.read();
    return int(data)

def get_uid(user):
    result = getpwnam(user).pw_uid
    return result


#https://stackoverflow.com/questions/41431882/live-stream-stdout-and-stdin-with-websocket
## panel threading install idea
#async def time(websocket, path):
#    script_name = 'script.py'
#    script = await websocket.recv()
#    with open(script_name, 'w') as script_file:
#        script_file.write(script)
#    with subprocess.Popen(['python3', '-u', script_name],
#                          stdout=subprocess.PIPE,
#                          bufsize=1,
#                          universal_newlines=True) as process:
#        for line in process.stdout:
#            line = line.rstrip()
#            print(f"line = {line}")
#            await websocket.send(line)