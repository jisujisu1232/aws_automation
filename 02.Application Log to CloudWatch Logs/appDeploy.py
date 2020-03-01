# Author: Jisu Kim
# Date last modified: 2019/02/20
# Python Version: 2.7
'''
Arguments
    1 : CloudWatch LogGroup Name
ec2 IAM Role
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "logs:PutMetricFilter",
                "logs:CreateLogStream",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams",
                "logs:GetLogEvents",
                "logs:PutRetentionPolicy",
                "logs:PutLogEvents",
                "logs:CreateLogGroup"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:*:*"
        },
        {
            "Sid": "VisualEditor1",
            "Effect": "Allow",
            "Action": [
                "sns:Publish",
                "ec2:TerminateInstances",
                "ec2:DescribeTags",
                "autoscaling:DetachInstances",
                "s3:GetObject",
                "s3:GetObjectVersion"
            ],
            "Resource": "*"
        }
    ]
}
'''

import shlex
import subprocess
import json
import sys
import os
import traceback
import time
repetitions = 3
def returnValue(command_line):
    for i in range(repetitions):
        try:
            returnV = subprocess.check_output(shlex.split(command_line))
            break
        except Exception, e:
            if i == repetitions-1:
                raise e
    return returnV

def deployTagCheck(prefix, str):
    if (len(str)-len(prefix))==1:
        idx = str[len(prefix):]
        if idx in numberStr:
            return int(idx)
    return False
def detachAndTerminate(errMsg, isDecrementDesire):
    errSub = '[Error in Instance]'
    if isDecrementDesire:
        errSub = errSub + 'Access Denied or Another. '
    else:
        errSub = errSub + 'Read timed out. '

    errPrefix = ''
    if instance_id:
        errPrefix = errPrefix + 'InstanceId : '+instance_id
    if asgName:
        errPrefix = errPrefix + ', AutoScalingGroup Name : '+asgName
    if region:
        errPrefix = errPrefix + ', region : '+region
    errPrefix = errPrefix +'\n\n'
    try:
        if asgName:
            decreStr = '--no-should-decrement-desired-capacity'
            if isDecrementDesire:
                decreStr = '--should-decrement-desired-capacity'
            returnValue('aws autoscaling detach-instances --region '+region+' --instance-ids '+instance_id+' --auto-scaling-group-name '+asgName+' '+decreStr)
            returnValue('aws ec2 terminate-instances --region '+region+' --instance-ids '+instance_id)
            if isDecrementDesire:
                errPrefix = errPrefix + 'DesiredCapacity of ASG decreased by 1.\n\nCheck the network or EC2 IAM Role or tags of ASG.\n\n'
            else:
                errPrefix = errPrefix + 'This instance is detached from ASG and then terminated and the new instance is launched by ASG.\n\n'
    except Exception, e:
        errMsg = errMsg + '\n\n'+str(e)
    errMsg = errPrefix + errMsg
    sendToAdmin(errSub, errMsg)

def sendToAdmin(errSub, errMsg):
    returnValue('aws sns publish --region '+region+' --topic-arn "'+AdminTopicArn+'" --message "'+errMsg+'" --subject "'+errSub+'"')
region = returnValue("curl -sq http://169.254.169.254/latest/meta-data/placement/availability-zone/")
region = region[:len(region)-1]
instance_id = returnValue("curl -s http://169.254.169.254/latest/meta-data/instance-id")
print instance_id
#get tags for get version
tags = json.loads(returnValue('aws ec2 describe-tags --region '+region+' --filters "Name=resource-id,Values='+instance_id+'"'))
s3VersionIdApp = 's3versionidapp'
s3Key = 'apps3key'
AppPath = 'apppath'

asgName = None
bucket = False
s3VersionIdApps = []
s3Keys = []
AppPaths = []
numberStr = '123456789'
osUser = False
osGroup = False
logPathsKey = False
AdminTopicArn = False
for i in range(9):
    s3VersionIdApps.append(False)
    s3Keys.append(False)
    AppPaths.append(False)
isInError = False
for tag in tags['Tags']:
    isInError = False
    errKey = False
    key = tag.get('Key').lower()
    if key=='aws:autoscaling:groupname':
        asgName = tag.get('Value')
    elif key=='bucket':
        bucket = tag.get('Value')
    elif key=='osappuser':
        osUser = tag.get('Value')
    elif key=='osappgroup':
        osGroup = tag.get('Value')
    elif key=='logpaths3key':
        logPathsKey = tag.get('Value')
    elif key=='admintopicarn':
        AdminTopicArn = tag.get('Value')
    elif key.startswith(s3VersionIdApp):
        errKey = s3VersionIdApp
        idx = deployTagCheck(s3VersionIdApp, key)
        if idx:
            s3VersionIdApps[idx-1]=tag.get('Value')
        else:
            isInError = True
    elif key.startswith(s3Key):
        errKey = s3Key
        idx = deployTagCheck(s3Key, key)
        if idx:
            s3Keys[idx-1]=tag.get('Value')
        else:
            isInError = True
    elif key.startswith(AppPath):
        errKey = AppPath
        idx = deployTagCheck(AppPath, key)
        if idx:
            AppPaths[idx-1]=tag.get('Value')
        else:
            isInError = True
    if isInError:
        print 'Failed: '+tag.get('Key')+' not [1-9]'

logPathFile="/root/logPathFile.txt"
if bucket:
    print "[Start App Deploy]"
    isInError = True
    executeTime = time.time()
    try:
        for path in AppPaths:
            if path:
                if '*' in path:
                    print 'Error : Asterisk in App path.'
                    exit('False')
                returnValue("rm -f "+path)
        for index in range(len(s3Keys)):
            if s3Keys[index] and s3VersionIdApps[index] and AppPaths[index]:
                executeTime = time.time()
                returnValue("aws s3api get-object --region "+region+" --bucket "+bucket+" --key "+s3Keys[index]+" --version-id "+s3VersionIdApps[index]+" "+AppPaths[index])
                if osUser and osGroup:
                    returnValue("chown "+osUser+"."+osGroup+" "+AppPaths[index])
                print "[Deploy Success] : "+AppPaths[index]
        print "[END App Deploy]"
        print "[Start Log Setting]"
        if logPathsKey:
            executeTime = time.time()
            returnValue("aws s3api get-object --region "+region+" --bucket "+bucket+" --key "+logPathsKey+" "+logPathFile)
        else:
            print "logPathsKey not in tags"
        isInError = False
    except Exception, e:
        #(time.time()-executeTime)<60
        #False -> Read timed out
        #True Access Denied or another Error
        detachAndTerminate(str(e), (time.time()-executeTime)<60)
    if not isInError:
        if os.path.isfile(logPathFile):
            confFilePath="/etc/awslogs/awslogs.conf"
            if not os.path.isfile(confFilePath):
                confFilePath="/var/awslogs/etc/awslogs.conf"
            logPathTxt=open(logPathFile, 'r')
            logPathContent = logPathTxt.read()
            logPathTxt.close()
            logPaths = logPathContent.split()
            returnArr = []
            isInAsterisk=False
            asteriskReplaceStr="Asterisk"
            for logPath in logPaths:
                try:
                    if "*" in logPath:
                        isInAsterisk=True
                    tempLogPath=logPath
                    if not os.path.isfile(logPath):
                        if not logPath.startswith('/'):
                            logPath='/'+logPath
                        logFolders=logPath[1:].split('/')
                        path=""
                        logFoldersLen=len(logFolders)
                        for index in range(logFoldersLen):
                            if index == (logFoldersLen-1):
                                break
                            folder=logFolders[index]
                            if isInAsterisk:
                                if folder=="*":
                                    folder=asteriskReplaceStr
                            path+="/"+folder
                            if not os.path.isdir(path):
                                returnValue("mkdir "+path)
                            returnValue("chown "+osUser+"."+osGroup+" "+path)
                        if isInAsterisk:
                            tempLogPath=tempLogPath.replace('*',asteriskReplaceStr)
                        returnValue("touch "+tempLogPath)
                        if osUser and osGroup:
                            returnValue("chmod 777 "+tempLogPath)
                            returnValue("chown "+osUser+"."+osGroup+" "+tempLogPath)
                            print osUser+"."+osGroup+" "+tempLogPath
                        returnValue("chmod 644 "+tempLogPath)
                    if logPath in returnArr:
                        print 'Error : '+logPath+' already in '+confFilePath
                    else:
                        returnArr.append(logPath)
                        if os.path.isfile(logPath) or isInAsterisk:
                            print logPath
                            if not isInAsterisk:
                                f = open(logPath, 'r+')
                                f.truncate(0)
                                f.close()
                            logConfFile = open(confFilePath,'a')
                            logConfFile.write('['+tempLogPath+']\n')
                            #logConfFile.write("datetime_format = %b %d %H:%M:%S\n")
                            logConfFile.write("buffer_duration = 5000\n")
                            logConfFile.write("batch_size = 1048576\n")
                            logConfFile.write("batch_count = 10000\n")
                            logConfFile.write("log_stream_name = "+tempLogPath+"({instance_id})\n")
                            logConfFile.write("initial_position = end_of_file\n")
                            logConfFile.write("file = "+logPath+"\n")
                            logConfFile.write("log_group_name = "+sys.argv[1]+"\n\n")
                            logConfFile.close()
                            print 'Success : '+logPath
                except:
                    traceback.print_exc()
                    print logPath+" has error"
            #For return to ShellScript

            print "[End Log Setting]"
        else:
            print 'logPathFile is not exist.'
else:
    print 'Tag Key "bucket" is not exist'
