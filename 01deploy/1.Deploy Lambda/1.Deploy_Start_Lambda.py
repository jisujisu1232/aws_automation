# Author: Jisu Kim
# Date created: 2018/07/05
# Date last modified: 2018/09/06
# Python Version: 2.7
'''
timeout : 5min 0sec

Reserve concurrency : 1


[Environment variables]
key             Value
topicArn        {snsTopicArn in admin's email}
triggerTopicArn {snsTopicArn in trigger lambda}
errorLambdaName {errorHandling Lambda Name}

iam policy
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction",
                "lambda:ListVersionsByFunction",
                "lambda:ListTags",
                "sns:Publish",
                "sns:ListSubscriptionsByTopic",
                "s3:ListBucketVersions",
                "autoscaling:DescribeAutoScalingNotificationTypes",
                "autoscaling:DeleteNotificationConfiguration",
                "autoscaling:AttachLoadBalancers",
                "autoscaling:DetachLoadBalancers",
                "autoscaling:DescribeAutoScalingGroups",
                "autoscaling:UpdateAutoScalingGroup",
                "autoscaling:DescribeNotificationConfigurations",
                "autoscaling:PutNotificationConfiguration",
                "autoscaling:DetachLoadBalancerTargetGroups",
                "autoscaling:AttachLoadBalancerTargetGroups",
                "autoscaling:CreateOrUpdateTags",
                "autoscaling:DescribeScheduledActions",
                "autoscaling:PutScheduledUpdateGroupAction",
                "autoscaling:BatchPutScheduledUpdateGroupAction",
                "autoscaling:DeleteScheduledAction",
                "autoscaling:BatchDeleteScheduledAction",
                "elasticloadbalancing:DescribeInstanceHealth",
                "elasticloadbalancing:CreateTargetGroup",
                "elasticloadbalancing:AddTags",
                "elasticloadbalancing:ConfigureHealthCheck",
                "elasticloadbalancing:CreateListener",
                "elasticloadbalancing:DescribeListeners",
                "elasticloadbalancing:DeleteLoadBalancer",
                "elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:CreateLoadBalancer",
                "elasticloadbalancing:DescribeTags",
                "elasticloadbalancing:DeleteTargetGroup",
                "elasticloadbalancing:DescribeTargetHealth",
                "elasticloadbalancing:DescribeTargetGroups",
                "elasticloadbalancing:DeleteListener"
            ],
            "Resource": "*"
        },
        {
            "Sid": "VisualEditor1",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Sid": "VisualEditor2",
            "Effect": "Allow",
            "Action": "logs:CreateLogGroup",
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}
'''
import boto3
import traceback
import json
import random
import string
import datetime
import os

def lambda_handler(event, context):
    numberStr = '123456789'
    s3VersionIdApp = 's3versionidapp'
    s3Key = 'apps3key'
    versionParams = 'versionParams'
    AppPath = 'apppath'
    bucket='bucket'
    AutoScalingGroupName = 'AutoScalingGroupName'
    Task = 'taskfordeploy'
    MinSize = 'MinSize'
    MaxSize = 'MaxSize'
    DesiredCapacity = 'DesiredCapacity'
    typeStandBy = 'StandBy'
    typeActive = 'Active'
    Type = 'type'
    LoadBalancerNames = 'LoadBalancerNames'
    tempPrefix = 'deploycheck-'
    tempTaskTagName = 'deployTaskTemp'
    prevType = 'prevtype'
    TargetGroupARNs = 'TargetGroupARNs'
    Repetitions = 'repetitions'
    def responseCheck(response):
        try:
            if response.get('ResponseMetadata').get('HTTPStatusCode')!=200:
                print response.get('ResponseMetadata')
                return False
        except:
            return False
        return True
    def actionsByStatus(message, status_code):
        subject = ''
        msg = ''
        if status_code == 200:
            successMsg = '[Deploy] Start(Task : '+runType+') Called by '+caller
            subject = successMsg
            msg = successMsg
        else:
            subject = '[Failed] Deploy Start Failed(Task : '+runType+', errCode : '+str(status_code)+') Called by '+caller
            msg = message.get('message')
            if status_code>407:
                try:
                    if errorLambdaName:
                        callErrorHandling(runType, str(status_code), subject,msg)
                        return
                except:
                    traceback.print_exc()
                msg +='[errorHandlingFailed]\n\n'+ msg+'\n\nPlease Clean (task:' +runType +')\n\n'
        sendMessageToAdmin(subject, msg)

    def callErrorHandling(task, errCode, msgTitle, msgContent):
        lambdaClient = boto3.client('lambda')
        payload = {}
        payload['task']=task

        if topicArn:
            payload['topicArn']=topicArn
        if triggerTopicArn:
            payload['triggerTopicArn']=triggerTopicArn
        if not errCode and not msgTitle and not msgContent:
            payload['isSuccess']='True'
        payload['errCode']=errCode
        payload['msgTitle']=msgTitle
        payload['msgContent']=msgContent
        response = lambdaClient.list_versions_by_function(
            FunctionName=errorLambdaName
        )
        versionList = response['Versions']
        currVersion = versionList[0]
        for version in response['Versions']:
            if version['LastModified'] > currVersion['LastModified']:
                currVersion = version
        response = lambdaClient.invoke(
            FunctionName=errorLambdaName,
            InvocationType='Event',
            Payload=json.dumps(payload),
            Qualifier=currVersion['Version']
        )
        return response

    def sendMessageToAdmin(subject, message):
        try:
            if topicArn:
                snsClient = boto3.client("sns")
                response = snsClient.publish(
                    Subject = subject,
                    TopicArn = topicArn,
                    Message = message
                )
                if not responseCheck(response):
                    raise Exception
                print '[Send to Admin Success]'
            else:
                print '[Send to Admin Failed] This lambda does not have a topicArn tag.'
            return True
        except:
            print '[Send to Admin Failed]'
            traceback.print_exc()
            return False
    def responseReturn(message, status_code):
        actionsByStatus(message, status_code)
        return {
            'statusCode': str(status_code),
            'body': json.dumps(message),

            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
        }
    def tagsInASG(autoscalingGroup):
        resultTags = {}
        tags = autoscalingGroup['Tags']
        resultTags.update({AutoScalingGroupName : autoscalingGroup[AutoScalingGroupName]})
        resultTags.update({MinSize : autoscalingGroup[MinSize]})
        resultTags.update({MaxSize : autoscalingGroup[MaxSize]})
        resultTags.update({DesiredCapacity : autoscalingGroup[DesiredCapacity]})
        resultTags.update({LoadBalancerNames : autoscalingGroup[LoadBalancerNames]})
        resultTags.update({TargetGroupARNs : autoscalingGroup[TargetGroupARNs]})

        s3VersionIdApps = []
        s3Keys = []
        AppPaths = []
        versionIdParams=[]
        for i in range(10):
            s3VersionIdApps.append(False)
            s3Keys.append(False)
            AppPaths.append(False)
            versionIdParams.append(False)
        for tag in tags:
            isInError = False
            errKey = False
            key = tag.get('Key').lower()
            if key==bucket:
                resultTags.update({bucket : tag.get('Value')})
            elif key==Task:
                resultTags.update({Task : tag.get('Value')})
            elif key==Type:
                resultTags.update({Type : tag.get('Value')})
            elif key==Repetitions:
                resultTags.update({Repetitions : tag.get('Value')})
            elif key.startswith(s3VersionIdApp):
                idx = deployTagCheck(s3VersionIdApp, key)
                if idx:
                    s3VersionIdApps[idx-1]=tag.get('Value')
                else:
                    isInError = True
            elif key.startswith(s3Key):
                idx = deployTagCheck(s3Key, key)
                if idx:
                    s3Keys[idx-1]=tag.get('Value')
                else:
                    isInError = True
            elif key.startswith(AppPath):
                idx = deployTagCheck(AppPath, key)
                if idx:
                    AppPaths[idx-1]=tag.get('Value')
                else:
                    isInError = True
            if isInError:
                print 'Failed: '+tag.get('Key')+' not [1-9]'

        resultTags.update({s3VersionIdApp : s3VersionIdApps})
        resultTags.update({s3Key : s3Keys})
        resultTags.update({AppPath : AppPaths})
        resultTags.update({versionParams : versionIdParams})
        return resultTags

    def deployTagCheck(prefix, str):
        if (len(str)-len(prefix))==1:
            idx = str[len(prefix):]
            if idx in numberStr:
                return int(idx)
        return False

    def updateAppVersion(s3Client, asgClient, bucket, s3Key, s3VersionId, asgGroupName, tagKey, rollbackVersion):
        try:
            objects={}
            objects.update({'Versions':[]})
            nextKeyMaker = None
            nextVersionIdMarker = None
            while True:
                if nextKeyMaker:
                    response = s3Client.list_object_versions(
                        Bucket=bucket,
                        Prefix=s3Key,
                        MaxKeys=100,
                        KeyMarker=nextKeyMaker,
                        VersionIdMarker=nextVersionIdMarker
                    )
                else:
                    response = s3Client.list_object_versions(
                        Bucket=bucket,
                        Prefix=s3Key,
                        MaxKeys=100
                    )
                if not responseCheck(response):
                    return False
                objects['Versions'] = objects['Versions']+response['Versions']
                if response.get('NextVersionIdMarker') and response.get('NextKeyMarker'):
                    nextKeyMaker = response.get('NextKeyMarker')
                    nextVersionIdMarker = response.get('NextVersionIdMarker')
                else:
                    break
            if len(objects['Versions'])==0:
                print "s3 Key is not exist"
                return False
            else:
                versionId = None
                for version in objects['Versions']:
                    if version['Key'] == s3Key:
                        if rollbackVersion:
                            if version['VersionId'] == rollbackVersion:
                                versionId = version['VersionId']
                                break
                        elif version['IsLatest']:
                            versionId = version['VersionId']
                            break
                if versionId:
                    if versionId != s3VersionId:
                        tags = []
                        tags.append(makeTagForASG(asgGroupName, tagKey, versionId, True))
                        if not updateASGTags(asgClient, tags):
                            return False
                else:
                    return False
                print s3Key +" version is "+ versionId
        except:
            traceback.print_exc()
            return False
        return True
    def updateASGTags(asgClient, tags):
        return asgClient.create_or_update_tags(
            Tags=tags
        )
    def makeTagForASG(asgGroupName, tagKey, tagValue, PropagateAtLaunch):
        return {
            'ResourceId':asgGroupName,
            'ResourceType': 'auto-scaling-group',
            'Key': tagKey,
            'Value': tagValue,
            'PropagateAtLaunch': PropagateAtLaunch
        }
    def makeTempName():
        tempName = tempPrefix
        for i in range(20):
            tempName += random.choice(string.ascii_lowercase)
        return tempName
    def getTargetGroupNameFromArn(tgArn):
        return getNameFromArn(tgArn, 1)
    def getLBNameFromArn(lbArn):
        return getNameFromArn(lbArn, 2)
    def getNameFromArn(arn, i):
        return (arn.split(':')[5]).split('/')[i]
    def deleteAllTestResource(elbClient, testELBNames, elbV2Client, testLBArns, testTGARNs):
        deleteCLBs(elbClient,testELBNames)
        for testLBArn in testLBArns:
            response = elbV2Client.describe_listeners(
                LoadBalancerArn=testLBArn
            )
            for listner in response['Listeners']:
                response = elbV2Client.delete_listener(
                    ListenerArn=listner['ListenerArn']
                )
        for testLBArn in testLBArns:
            response = elbV2Client.delete_load_balancer(
                LoadBalancerArn=testLBArn
            )
        for testTGArn in testTGARNs:
            response = elbV2Client.delete_target_group(
                TargetGroupArn=testTGArn
            )

    def deleteCLBs(client,clbNames):
        for clbName in clbNames:
            response = client.delete_load_balancer(
                LoadBalancerName=clbName
            )
    def updateActiveASGSchedules(asgClient, activeAsgName, numberOfRepetitions):
        if numberOfRepetitions == None or int(numberOfRepetitions) <2:
            numberOfRepetitions = 2
        else:
            numberOfRepetitions = int(numberOfRepetitions)
        response = asgClient.describe_scheduled_actions(
            AutoScalingGroupName=activeAsgName
        )
        schedules = response.get('ScheduledUpdateGroupActions')
        if schedules:
            for schedule in schedules:
                scheduleArgs = {}
                defaultStartTime = datetime.datetime.utcnow().replace(tzinfo=None)+datetime.timedelta(minutes=(numberOfRepetitions+1)*10)
                scheduleArgs.update({'AutoScalingGroupName':schedule.get('AutoScalingGroupName')})
                if schedule.get('ScheduledActionName') != None:
                    scheduleArgs.update({'ScheduledActionName':schedule.get('ScheduledActionName')})
                if schedule.get('StartTime') != None:
                    startTime = schedule.get('StartTime').replace(tzinfo=None)
                    if startTime == None or startTime < defaultStartTime:
                        startTime = defaultStartTime
                    scheduleArgs.update({'StartTime':startTime})
                if schedule.get('EndTime') != None:
                    endTime = schedule.get('EndTime').replace(tzinfo=None)
                    if defaultStartTime > endTime:
                        asgClient.delete_scheduled_action(
                            AutoScalingGroupName=activeAsgName,
                            ScheduledActionName=schedule.get('ScheduledActionName')
                        )
                        continue
                    scheduleArgs.update({'EndTime':endTime})
                if schedule.get('Recurrence') != None:
                    scheduleArgs.update({'Recurrence':schedule.get('Recurrence')})
                if schedule.get('MinSize') != None:
                    scheduleArgs.update({'MinSize':schedule.get('MinSize')})
                if schedule.get('MaxSize') != None:
                    scheduleArgs.update({'MaxSize':schedule.get('MaxSize')})
                if schedule.get('DesiredCapacity') != None:
                    scheduleArgs.update({'DesiredCapacity':schedule.get('DesiredCapacity')})
                asgClient.put_scheduled_update_group_action(**scheduleArgs)

    try:
        asgClient = boto3.client('autoscaling')
        s3Client = boto3.client('s3')
        elbClient = boto3.client('elb')
        elbV2Client = boto3.client('elbv2')
        count = 0
        StandByAsg = {}
        ActiveAsg = {}
        caller = event.get('caller')
        runType = event.get('runType')
        if not runType:
            runType = event['task']
        if not caller:
            caller = 'ADMIN'
        versions = event.get('versions')
        ldArn = context.invoked_function_arn
        resourceArn = ldArn[:ldArn.rfind(':')]
        if resourceArn.endswith(':function'):
            resourceArn = ldArn
        topicArn = os.environ['topicArn']
        errorLambdaName = os.environ['errorLambdaName']
        triggerTopicArn = os.environ['triggerTopicArn']
        response = asgClient.describe_auto_scaling_groups()
        for i in response['AutoScalingGroups']:
            tags = tagsInASG(i)
            if tags.get(Task) == runType:
                if typeStandBy == tags.get(Type):
                    StandByAsg = tags
                    count = count + 1
                    StandByAsg.update({'Instances':len(i['Instances'])})
                elif typeActive == tags.get(Type):
                    ActiveAsg = tags
                    count = count + 1
                if count == 2:
                    break
        if count != 2:
            cc=' and '
            if count:
                cc=' or '
            errMsg = 'Has no Active '+cc+' StandBy ASG'
            print errMsg
            return responseReturn({'message': errMsg}, 400)

        print ActiveAsg.get(AutoScalingGroupName) + ' is Active'
        print StandByAsg.get(AutoScalingGroupName) + ' is StandBy'
        if StandByAsg.get(DesiredCapacity) != 0 or StandByAsg.get(DesiredCapacity)!=StandByAsg.get('Instances'):
            return responseReturn({'message': 'StandBy ASG Instances is not Zero or not equal to DesiredCapacity'}, 401)
        updateActiveASGSchedules(asgClient, ActiveAsg.get(AutoScalingGroupName), StandByAsg.get(Repetitions))
        '''
        update StandBy Tags
        Copy tags of Active to StandBy
        tags = []
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), s3VersionIdApp1, ActiveAsg.get(s3VersionIdApp1), True))
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), s3VersionIdApp2, ActiveAsg.get(s3VersionIdApp2), True))
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), s3Key1, ActiveAsg.get(s3Key1), True))
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), s3Key2, ActiveAsg.get(s3Key2), True))
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), AppPath1, ActiveAsg.get(AppPath1), True))
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), AppPath2, ActiveAsg.get(AppPath2), True))
        tags.append(makeTagForASG(StandByAsg.get(AutoScalingGroupName), bucket, ActiveAsg.get(bucket), True))

        if updateASGTag(asgClient, tags):
            print 'Copy tags of Active to StandBy Success'
        resultTags.update({s3VersionIdApp : s3VersionIdApps})
        resultTags.update({s3Key : s3Keys})
        resultTags.update({AppPath : AppPaths})
        '''

        #Set AppVersion to latest
        versionArr = None
        isDoneUpdateAppVersion = True
        if versions:
            versionArr = versions.split(',')
            for i in range(len(versionArr)):
                StandByAsg.get(versionParams)[i]=versionArr[i].strip()
        for index in range(len(StandByAsg.get(s3Key))):
            if StandByAsg.get(s3Key)[index] and StandByAsg.get(s3VersionIdApp)[index] and StandByAsg.get(AppPath)[index]:
                result = updateAppVersion(s3Client, asgClient, StandByAsg.get(bucket), StandByAsg.get(s3Key)[index], StandByAsg.get(s3VersionIdApp)[index], StandByAsg.get(AutoScalingGroupName), s3VersionIdApp+str(index+1), StandByAsg.get(versionParams)[index])
                if not result:
                    isDoneUpdateAppVersion = False
                    errMsg = StandByAsg.get(bucket) +' key('+StandByAsg.get(s3Key)[index]+') has no '
                    if StandByAsg.get(versionParams)[index]:
                        errMsg = errMsg + 'versionId('+StandByAsg.get(versionParams)[index]+')'
                    else:
                        errMsg = errMsg + 'version or Update Failed'
                    break
        if isDoneUpdateAppVersion:
            print 'App Version Update Success'
        else:
            return responseReturn({'message': errMsg}, 402)
        '''
        create testELB
        sb asg -> detach lb -> (if old testELB is exist delete old testELB) -> attach testELB
        '''
        if len(ActiveAsg.get(LoadBalancerNames))==0 and len(ActiveAsg.get(TargetGroupARNs))==0:
            errMsg =  ActiveAsg['AutoScalingGroupName'] +'(Active) is not attach to ELB and TargetGroup'
            print errMsg
            return responseReturn({'message': errMsg}, 403)

        for testTGArn in ActiveAsg.get(TargetGroupARNs):
            if getTargetGroupNameFromArn(testTGArn).startswith(tempPrefix):
                return responseReturn({'message': 'Attached resource name startswith '+tempPrefix+' Check your previous deployment.'}, 404)
        for testELBName in ActiveAsg.get(LoadBalancerNames):
            if testELBName.startswith(tempPrefix):
                return responseReturn({'message': 'Attached resource name startswith '+tempPrefix+' Check your previous deployment.'}, 405)

        testELBNames = []
        if len(ActiveAsg.get(LoadBalancerNames))>0:
            response = elbClient.describe_load_balancers(
                LoadBalancerNames = ActiveAsg.get(LoadBalancerNames),
            )

            elbs= response.get('LoadBalancerDescriptions')
            existsDeployCLBs=[]
            activeELBs=[]
            healthCheckList=[]
            for lb in elbs:
                if lb['LoadBalancerName'].startswith(tempPrefix):
                    existsDeployCLBs.append(lb['LoadBalancerName'])
                elif lb['LoadBalancerName'] in ActiveAsg.get(LoadBalancerNames):
                    activeELBs.append(lb)
                    healthCheckList.append(lb['HealthCheck'])
            if len(activeELBs)==0:
                for elbName in ActiveAsg.get(LoadBalancerNames):
                    print elbName + ' attach by '+ActiveAsg[AutoScalingGroupName] +'(Active) is not exist'
                return responseReturn({'message': ActiveAsg[AutoScalingGroupName] +'(Active) is not attach to ELB'}, 406)

            for idx in range(len(activeELBs)):
                isPass = False
                for i in range(15):
                    testELBName = makeTempName()
                    if testELBName in existsDeployCLBs or testELBName in testELBNames:
                        continue
                    else:
                        testELBNames.append(testELBName)
                        isPass=True
                        break
                if not isPass:
                    deleteCLBs(elbClient,testELBNames)
                    return responseReturn({'message': 'Failed in make tempId. Please rerun'}, 407)
            for i, activeELB in enumerate(activeELBs):
                tempActiveELBListners = []
                for listner in activeELB['ListenerDescriptions']:
                    tempActiveELBListners.append(listner['Listener'])
                tempAZs = activeELB['AvailabilityZones']
                tempSubnets = activeELB['Subnets']
                if tempSubnets:
                    elbClient.create_load_balancer(
                        LoadBalancerName=testELBNames[i],
                        Listeners=tempActiveELBListners,
                        #AvailabilityZones=activeELB['AvailabilityZones'],
                        Subnets=tempSubnets,
                        SecurityGroups=activeELB['SecurityGroups'],
                        Scheme=activeELB['Scheme']
                    )
                else:
                    elbClient.create_load_balancer(
                        LoadBalancerName=testELBNames[i],
                        Listeners=tempActiveELBListners,
                        AvailabilityZones=tempAZs,
                        #Subnets=activeELB['Subnets'],
                        SecurityGroups=activeELB['SecurityGroups'],
                        Scheme=activeELB['Scheme']
                    )
                response = elbClient.configure_health_check(
                    LoadBalancerName=testELBNames[i],
                    HealthCheck={
                        'Target': healthCheckList[i]['Target'],
                        'Interval': healthCheckList[i]['Interval'],
                        'Timeout': healthCheckList[i]['Timeout'],
                        'UnhealthyThreshold': healthCheckList[i]['UnhealthyThreshold'],
                        'HealthyThreshold': healthCheckList[i]['HealthyThreshold']
                    }
                )
                response = elbClient.add_tags(
                    LoadBalancerNames=[
                        testELBNames[i]
                    ],
                    Tags=[
                        {
                            'Key': tempTaskTagName,
                            'Value': runType
                        },
                    ]
                )
            if len(StandByAsg[LoadBalancerNames]) > 0:
                response = asgClient.detach_load_balancers(
                    AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                    LoadBalancerNames=StandByAsg[LoadBalancerNames]
                )
            response = asgClient.attach_load_balancers(
                AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                LoadBalancerNames=testELBNames
            )
        testTGARNs = []
        testLBArns = []
        if len(ActiveAsg.get(TargetGroupARNs))>0:

            response = elbV2Client.describe_target_groups()
            targetGroups= response.get('TargetGroups')
            existsDeployTGs=[]
            activeTGs=[]
            for tg in targetGroups:
                if tg['TargetGroupName'].startswith(tempPrefix):
                    existsDeployTGs.append(tg['TargetGroupName'])
                elif tg['TargetGroupArn'] in ActiveAsg.get(TargetGroupARNs):
                    activeTGs.append(tg)
            if len(activeTGs)==0:
                for targetGroup in ActiveAsg.get(TargetGroupARNs):
                    print targetGroup + ' attach by '+ActiveAsg[AutoScalingGroupName] +'(Active) is not exist'
                return responseReturn({'message': ActiveAsg[AutoScalingGroupName] +'(Active) is not attach to Target Group'}, 408)
            testTGNames = []
            testTGLBMapping = []
            testLBMapping = {}
            for idx in range(len(activeTGs)):
                isPass = False
                for i in range(15):
                    tempTGName = makeTempName()
                    if tempTGName in existsDeployTGs or tempTGName in testTGNames:
                        continue
                    else:
                        testTGNames.append(tempTGName)
                        isPass=True
                        break
                if not isPass:
                    deleteCLBs(elbClient,testELBNames)
                    return responseReturn({'message': 'Failed in make tempId. Please rerun'}, 409)
            for i, activeTG in enumerate(activeTGs):
                response = None
                #NLB
                if activeTG['Protocol'].lower() =='tcp':
                    response = elbV2Client.create_target_group(
                        Name=testTGNames[i],
                        Protocol=activeTG['Protocol'],
                        Port=activeTG['Port'],
                        VpcId=activeTG['VpcId'],
                        HealthCheckProtocol=activeTG['HealthCheckProtocol'],
                        HealthCheckPort=activeTG['HealthCheckPort'],
                        HealthCheckIntervalSeconds=activeTG['HealthCheckIntervalSeconds'],
                        HealthCheckTimeoutSeconds=activeTG['HealthCheckTimeoutSeconds'],
                        HealthyThresholdCount=activeTG['HealthyThresholdCount'],
                        UnhealthyThresholdCount=activeTG['UnhealthyThresholdCount'],
                        TargetType=activeTG['TargetType']
                    )
                #ALB
                else:
                    response = elbV2Client.create_target_group(
                        Name=testTGNames[i],
                        Protocol=activeTG['Protocol'],
                        Port=activeTG['Port'],
                        VpcId=activeTG['VpcId'],
                        HealthCheckProtocol=activeTG['HealthCheckProtocol'],
                        HealthCheckPort=activeTG['HealthCheckPort'],
                        HealthCheckPath=activeTG['HealthCheckPath'],
                        HealthCheckIntervalSeconds=activeTG['HealthCheckIntervalSeconds'],
                        HealthCheckTimeoutSeconds=activeTG['HealthCheckTimeoutSeconds'],
                        HealthyThresholdCount=activeTG['HealthyThresholdCount'],
                        UnhealthyThresholdCount=activeTG['UnhealthyThresholdCount'],
                        Matcher=activeTG['Matcher'],
                        TargetType=activeTG['TargetType']
                    )
                for tg in response['TargetGroups']:
                    testTGARNs.append(tg['TargetGroupArn'])
                    tempMap = False
                    for map in testTGLBMapping:
                        if map.get('Key')==tg['TargetGroupArn']:
                            if type(map.get('Value')) == type([]):
                                tempMap = True
                                break
                    if not tempMap:
                        testTGLBMapping.append({'Key':tg['TargetGroupArn'],'Value':activeTG['LoadBalancerArns']})
                        response = elbV2Client.add_tags(
                            ResourceArns=[
                                tg['TargetGroupArn']
                            ],
                            Tags=[
                                {
                                    'Key': tempTaskTagName,
                                    'Value': runType
                                }
                            ]
                        )
            for map in testTGLBMapping:
                for lbArn in map.get('Value'):
                    if type(testLBMapping.get(lbArn))==type(None):
                        lb = None
                        isPass = True
                        testLBName = None
                        for i in range(15):
                            isPass = True
                            testLBName = makeTempName()
                            response = elbV2Client.describe_load_balancers()
                            for dlb in response['LoadBalancers']:
                                if dlb['LoadBalancerArn']==lbArn:
                                    lb = dlb
                                elif getLBNameFromArn(dlb['LoadBalancerArn'])==testLBName:
                                    isPass=False
                                    break
                            if isPass:
                                testLBArns.append(testLBName)
                                break
                            else:
                                continue
                        if not isPass or not lb:
                            deleteAllTestResource(elbClient, testELBNames, elbV2Client, testLBArns, testTGARNs)
                            return responseReturn({'message': 'Failed in make tempId. Please rerun'}, 410)
                        Subnets = []
                        SubnetMappings = []
                        for az in lb['AvailabilityZones']:
                            SubnetMappings.append({'SubnetId':az.get('SubnetId'),'AllocationId':az.get('ZoneName')})
                            Subnets.append(az.get('SubnetId'))
                        if lb['Type']=='application':
                            response = elbV2Client.create_load_balancer(
                                Name=testLBName,
                                Subnets=Subnets,
                                #SubnetMappings=SubnetMappings,
                                SecurityGroups=lb['SecurityGroups'],
                                Scheme=lb['Scheme'],
                                Type=lb['Type'],
                                IpAddressType=lb['IpAddressType']
                            )
                        else:
                            response = elbV2Client.create_load_balancer(
                                Name=testLBName,
                                Subnets=Subnets,
                                Scheme=lb['Scheme'],
                                Type=lb['Type'],
                                IpAddressType=lb['IpAddressType']
                            )
                        createdLBArn = response['LoadBalancers'][0]['LoadBalancerArn']
                        testLBArns.append(createdLBArn)
                        testLBMapping.update({lbArn:createdLBArn})
                        response = elbV2Client.add_tags(
                            ResourceArns=[
                                createdLBArn
                            ],
                            Tags=[
                                {
                                    'Key': tempTaskTagName,
                                    'Value': runType
                                }
                            ]
                        )
                        response = elbV2Client.describe_listeners(
                            LoadBalancerArn=lbArn
                        )
                        for listner in response['Listeners']:
                            defaultActions = []
                            for action in listner['DefaultActions']:
                                tempAction = action
                                tempTGARN = None
                                for index in range(len(activeTGs)):
                                    if activeTGs[index]['TargetGroupArn']==action['TargetGroupArn']:
                                        tempTGARN = testTGARNs[index]
                                if tempTGARN:
                                    tempAction.update({'TargetGroupArn':tempTGARN})
                                    defaultActions.append(tempAction)
                            tempSslPolicy = ""
                            tempCertificates = []
                            if listner.get('SslPolicy'):
                                tempSslPolicy = listner['SslPolicy']
                            if listner.get('Certificates'):
                                tempCertificates = listner['Certificates']
                            response = elbV2Client.create_listener(
                                LoadBalancerArn=createdLBArn,
                                Protocol=listner['Protocol'],
                                Port=listner['Port'],
                                SslPolicy=tempSslPolicy,
                                Certificates=tempCertificates,
                                DefaultActions=defaultActions
                            )


            if len(StandByAsg[TargetGroupARNs]) > 0:
                response = asgClient.detach_load_balancer_target_groups(
                    AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                    TargetGroupARNs=StandByAsg[TargetGroupARNs]
                )
            response = asgClient.attach_load_balancer_target_groups(
                AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                TargetGroupARNs=testTGARNs
            )
        try:
            if not triggerTopicArn:
                raise Exception
            snsClient = boto3.client('sns')
            response = snsClient.list_subscriptions_by_topic(
                TopicArn=triggerTopicArn
            )
            isInLambda = False
            for sub in response['Subscriptions']:
                if sub['Protocol'].lower()=='lambda':
                    isInLambda = True
                    break
            if isInLambda:
                pass
            else:
                raise Exception
            response = asgClient.describe_notification_configurations(
                AutoScalingGroupNames=[
                    StandByAsg.get(AutoScalingGroupName)
                ]
            )
            notiConfigurations = response.get('NotificationConfigurations')
            isNotiIn = False
            if notiConfigurations:
                for nC in notiConfigurations:
                    if nC.get('TopicARN')==triggerTopicArn:
                        isNotiIn = True
                        response = asgClient.delete_notification_configuration(
                            AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                            TopicARN=nC.get('TopicARN')
                        )
            response = asgClient.create_or_update_tags(
                Tags=[
                    {
                    'ResourceId':ActiveAsg[AutoScalingGroupName],
                    'ResourceType': 'auto-scaling-group',
                    'Key': prevType,
                    'Value': typeActive,
                    'PropagateAtLaunch': False
                    },
                    {
                    'ResourceId': StandByAsg.get(AutoScalingGroupName),
                    'ResourceType': 'auto-scaling-group',
                    'Key': prevType,
                    'Value': typeStandBy,
                    'PropagateAtLaunch': False
                    }
                ]
            )
            if not isNotiIn:
                response = asgClient.describe_auto_scaling_notification_types()
                tempNotiTypeStr = None
                if response.get('AutoScalingNotificationTypes'):
                    for notiType in response.get('AutoScalingNotificationTypes'):
                        if notiType.lower().endswith('launch'):
                            tempNotiTypeStr = notiType
                            break
                if tempNotiTypeStr:
                    response = asgClient.put_notification_configuration(
                            AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                            NotificationTypes=[
                                tempNotiTypeStr
                            ],
                            TopicARN=triggerTopicArn,
                        )
        except:
            deleteAllTestResource(elbClient, testELBNames, elbV2Client, testLBArns, testTGARNs)
            msg = "Please Check triggerTopicArn tag("+triggerTopicArn+") is correct."
            print msg
            return responseReturn({'message': msg}, 411)

        if not responseCheck(response):
            deleteAllTestResource(elbClient, testELBNames, elbV2Client, testLBArns, testTGARNs)
            print "update auto scaling group is Failed"
            return responseReturn({'message': 'Error: update auto scaling group is Failed'}, 412)
        '''
        end

        when standby's instance launch call deploy trigger lambda

        '''
        print 'StandBy Autoscaling Group Update done'
    except:
        traceback.print_exc()
        return responseReturn({'message': 'Error: please check CloudWatch Logs for lambda('+context.function_name+')'}, 500)
    return responseReturn({'message': 'Success'}, 200)
