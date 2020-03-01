# Author: Jisu Kim
# Date created: 2018/08/21
# Date last modified: 2018/09/06
# Python Version: 2.7
'''
timeout : 5min 0sec
[Environment variables]
Key         Value
topicArn        {snsTopicArn in admin's email}
triggerTopicArn {snsTopicArn in trigger lambda}

iam
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
import json
import traceback
import datetime
import os
from time import sleep
def lambda_handler(event, context):
    class KnownException(Exception):
        def __init__(self, *args):
            self.args = [a for a in args]
    AutoScalingGroupName = 'AutoScalingGroupName'
    Task = 'taskfordeploy'
    MinSize = 'MinSize'
    MaxSize = 'MaxSize'
    DesiredCapacity = 'DesiredCapacity'
    typeStandBy = 'StandBy'
    typeActive = 'Active'
    Type = 'type'
    LoadBalancerNames = 'LoadBalancerNames'
    tempPrefix='deploycheck-'
    tempTaskTagName = 'deployTaskTemp'
    TargetGroupARNs = 'TargetGroupARNs'
    Repetitions = 'repetitions'
    prevType = 'prevtype'
    topicArn = None
    numberOfRepetitions = 2
    errorLambdaName = None
    errCode = None
    msgTitle = None
    msgContent = None
    isSuccess = None
    currentTask = 'None'
    def responseCheck(response):
        try:
            if response.get('ResponseMetadata').get('HTTPStatusCode')!=200:
                print response.get('ResponseMetadata')
                return False
        except:
            return False
        return True
    def responseReturn(message, status_code):
        return {
            'statusCode': str(status_code),
            'body': json.dumps(message),

            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
        }

    #ASG dict to One-dimensional dict
    def tagsInASG(autoscalingGroup):
        resultTags = {}
        tags = autoscalingGroup['Tags']
        resultTags.update({AutoScalingGroupName : autoscalingGroup[AutoScalingGroupName]})
        resultTags.update({MinSize : autoscalingGroup[MinSize]})
        resultTags.update({MaxSize : autoscalingGroup[MaxSize]})
        resultTags.update({DesiredCapacity : autoscalingGroup[DesiredCapacity]})
        resultTags.update({LoadBalancerNames : autoscalingGroup[LoadBalancerNames]})
        resultTags.update({TargetGroupARNs : autoscalingGroup[TargetGroupARNs]})

        for tag in tags:
            key=tag.get('Key').lower()
            if key==Task:
                resultTags.update({Task : tag.get('Value')})
            elif key==Type:
                resultTags.update({Type : tag.get('Value')})
            elif key==Repetitions:
                resultTags.update({Repetitions : tag.get('Value')})
            elif key==prevType:
                resultTags.update({prevType : tag.get('Value')})
        return resultTags

    #SNS alram to Admin using topicArn in lambda's tag
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

    def errorHandlingSuccess(isDeploy,msgTitle,msgContent):
        successMsg = '[Success]'
        if errCode or isSuccess:
            if not isSuccess and len(errCode)==3:
                msgContent = 'Please try again.\n\n'+msgContent
            elif isDeploy:
                successMsg = successMsg +' Non-disruptive deployment(Task : '+currentTask+')'
                msgTitle = successMsg
                if isSuccess:
                    msgContent = successMsg
                else:
                    msgContent = successMsg + '\n\n[Resolved Exception]\n'+'ErrCode : '+errCode+'\n'+msgContent
        else:
            successMsg = successMsg +' Deploy Clean(Task : '+currentTask+')'
            msgTitle = successMsg
            msgContent = successMsg
        if not isSuccess:
            msgContent = '[Error Handling Success]\n\n'+msgContent
        sendMessageToAdmin(msgTitle,msgContent)
        return responseReturn({'message': msgTitle}, 200)

    def errorHandlingFailed(msgTitle,msgContent):
        if not errCode:
            msgTitle = '[Failed] Deploy Clean(Task : '+currentTask+')'
            msgContent = 'Unknown Err. Please Check CloudWatch log '+context.function_name
        msgContent = '[Error Handling Failed]\n\n'+msgContent+'\n\nPlease execute clean or follow manual'
        sendMessageToAdmin('[Error]'+msgTitle, msgContent)
        return responseReturn({'message': msgTitle}, 400)
    def modifyAsg(asgClient, nextStandByAsgName, nextActiveAsgName):
        response = asgClient.update_auto_scaling_group(
            AutoScalingGroupName=nextStandByAsgName,
            MinSize=0,
            MaxSize=0,
            DesiredCapacity=0,
        )
        response = asgClient.create_or_update_tags(
            Tags=[
                {
                'ResourceId':nextActiveAsgName,
                'ResourceType': 'auto-scaling-group',
                'Key': Type,
                'Value': typeActive,
                'PropagateAtLaunch': False
                },
                {
                'ResourceId': nextStandByAsgName,
                'ResourceType': 'auto-scaling-group',
                'Key': Type,
                'Value': typeStandBy,
                'PropagateAtLaunch': False
                }
            ]
        )
        modifyAsgScheduledAction(asgClient, nextStandByAsgName, nextActiveAsgName)
        return True

    def modifyAsgScheduledAction(asgClient, nextStandByAsgName, nextActiveAsgName):
        response = asgClient.describe_scheduled_actions(
            AutoScalingGroupName=nextStandByAsgName
        )
        standbySchedules = response.get('ScheduledUpdateGroupActions')
        for schedule in standbySchedules:
            try:
                asgClient.delete_scheduled_action(
                    AutoScalingGroupName=nextStandByAsgName,
                    ScheduledActionName=schedule.get('ScheduledActionName')
                )
            except:
                asgClient.delete_scheduled_action(
                    AutoScalingGroupName=nextStandByAsgName,
                    ScheduledActionName=schedule.get('ScheduledActionName')
                )
            defaultStartTime = datetime.datetime.utcnow().replace(tzinfo=None)+datetime.timedelta(minutes=1)
            scheduleArgs = {}
            scheduleArgs.update({'AutoScalingGroupName':nextActiveAsgName})
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
            try:
                asgClient.put_scheduled_update_group_action(**scheduleArgs)
            except:
                asgClient.put_scheduled_update_group_action(**scheduleArgs)

    def detachAll(asgClient,asg):
        if asg[TargetGroupARNs]:
            response = asgClient.detach_load_balancer_target_groups(
                AutoScalingGroupName=asg[AutoScalingGroupName],
                TargetGroupARNs=asg[TargetGroupARNs]
            )
        if asg[LoadBalancerNames]:
            response = asgClient.detach_load_balancers(
                AutoScalingGroupName=asg[AutoScalingGroupName],
                LoadBalancerNames=asg[LoadBalancerNames]
            )
        return True
    '''
    type1
    test LB and TG delete + standby to 000
    T000
    T001
    T002
    T003
    T005
    T006

    type2
    standby to 000 + delete all test lb & tg
    T004

    type3
    standby to 000
    T007
    T012

    type4
    active to 000 + detach all real lb & tg swap Active/StandBy
    T008

    type5
    active to 000 swap Active/StandBy
    T009

    type6
    swap Active/StandBy
    T010

    type0
    app fail
    T011

    not exist Active or StandBy
    T013
    '''

    #Step and asgName in event are not exist when first call
    try:
        currentTask = event.get('task')
        asgClient = boto3.client('autoscaling')
        elbClient = boto3.client('elb')
        elbV2Client = boto3.client('elbv2')
        ActiveAsg = None
        StandByAsg = None
        errCode = event.get('errCode')
        isSuccess = event.get('isSuccess')
        if errCode:
            errCode = errCode[:4]
        topicArn = event.get('topicArn')
        triggerTopicArn = event.get('triggerTopicArn')
        if not topicArn or not triggerTopicArn:
            if not topicArn:
                topicArn = os.environ['topicArn']
            if not triggerTopicArn:
                triggerTopicArn = os.environ['triggerTopicArn']

        msgTitle = event.get('msgTitle')
        msgContent = event.get('msgContent')
        if not msgTitle:
            msgTitle = ''
        if not msgContent:
            msgContent = ''
        if currentTask and currentTask != 'None':
            rsp = asgClient.describe_auto_scaling_groups()

            for asg in rsp['AutoScalingGroups']:
                tags = tagsInASG(asg)
                if tags.get(Task) == currentTask:
                    if tags.get(prevType)==typeActive:
                        ActiveAsg = tags
                    elif tags.get(prevType)==typeStandBy:
                        StandByAsg = tags
            if not ActiveAsg or not StandByAsg:
                return responseReturn({'message': 'PASS'}, 200)
        else:
            return responseReturn({'message': 'PASS'}, 200)
        '''
        type0 = ['T011','T013']
        type1 = ['T000',
                'T001',
                'T002',
                'T003',
                'T005',
                'T006']
        type2 = ['T004']
        type3 = ['T007',
                'T012']
        type4 = ['T008']
        type5 = ['T009']
        type6 = ['T010']
        if errCode in type0:
            return responseReturn({'message': 'PASS'}, 200)
        elif errCode in type1:
            test LB and TG delete + standby to 000
        elif errCode in type2:
            standby to 000 + delete all test lb & tg
        elif errCode in type3:
            standby to 000
        elif errCode in type4:
            active to 000 + detach all real lb & tg swap Active/StandBy
        elif errCode in type5:
            active to 000 swap Active/StandBy
        elif errCode in type6:
            swap Active/StandBy
        '''
        if triggerTopicArn:
            try:
                response = asgClient.delete_notification_configuration(
                    AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                    TopicARN=triggerTopicArn
                )
            except:
                print StandByAsg.get(AutoScalingGroupName) +' has no trigger notification or delete noti failed'
        #1. test lb/tg delete using tag name task
        response = elbV2Client.describe_load_balancers()
        LBs = response.get('LoadBalancers')
        for lb in LBs:
            if lb.get('LoadBalancerName').startswith(tempPrefix):
                response = elbV2Client.describe_tags(
                    ResourceArns=[
                        lb.get('LoadBalancerArn')
                    ]
                )
                tags = response.get('TagDescriptions')[0]['Tags']
                for tag in tags:
                    if tag['Key']==tempTaskTagName:
                        if tag['Value']==currentTask:
                            listnerResponse = elbV2Client.describe_listeners(
                                LoadBalancerArn=lb.get('LoadBalancerArn')
                            )
                            for listner in listnerResponse['Listeners']:
                                elbV2Client.delete_listener(
                                    ListenerArn=listner['ListenerArn']
                                )
                            elbV2Client.delete_load_balancer(
                                LoadBalancerArn=lb.get('LoadBalancerArn')
                            )
                        break
        response = elbClient.describe_load_balancers()
        for clb in response.get('LoadBalancerDescriptions'):
            if clb.get('LoadBalancerName').startswith(tempPrefix):
                response = elbClient.describe_tags(
                    LoadBalancerNames=[
                        clb.get('LoadBalancerName')
                    ]
                )
                tags = response.get('TagDescriptions')[0]['Tags']
                for tag in tags:
                    if tag['Key']==tempTaskTagName:
                        if tag['Value']==currentTask:
                            response = elbClient.delete_load_balancer(
                                LoadBalancerName=clb.get('LoadBalancerName')
                            )
                        break

        response = elbV2Client.describe_target_groups()
        TGs = response.get('TargetGroups')
        for lb in TGs:
            if lb.get('TargetGroupName').startswith(tempPrefix):

                response = elbV2Client.describe_tags(
                    ResourceArns=[
                        lb.get('TargetGroupArn')
                    ]
                )
                tags = response.get('TagDescriptions')[0]['Tags']
                for tag in tags:
                    if tag['Key']==tempTaskTagName:
                        if tag['Value']==currentTask:
                            response = elbV2Client.delete_target_group(
                                TargetGroupArn=lb.get('TargetGroupArn')
                            )
                        break
        '''
        2. a,s attached lb/tg and desire check

            - only a -> s to 000
            - only s -> a to 000 and type swap / deploy success
            - both a,s
                number of attached
                - a size >= s size
                    - a's desire > 0 s to 000 and detach
                    - s's desire > 0 a to 000 and detach / deploy success
                - s size > a size -> a to 000 and detach / deploy success
        '''
        aSize = len(ActiveAsg[LoadBalancerNames])+len(ActiveAsg[TargetGroupARNs])
        sSize = len(StandByAsg[LoadBalancerNames])+len(StandByAsg[TargetGroupARNs])
        isDeploy=False
        if aSize and sSize:
            if aSize >= sSize:
                if ActiveAsg[DesiredCapacity]>0:
                    if detachAll(asgClient, StandByAsg):
                        modifyAsg(asgClient, StandByAsg.get(AutoScalingGroupName), ActiveAsg[AutoScalingGroupName])
                elif StandByAsg[DesiredCapacity]>0:
                    if detachAll(asgClient, ActiveAsg):
                        modifyAsg(asgClient, ActiveAsg.get(AutoScalingGroupName), StandByAsg.get(AutoScalingGroupName))
                        isDeploy = True
                else:
                    pass
                    #It does not exist if it is not modified at console.
            else:
                if detachAll(asgClient, ActiveAsg):
                    modifyAsg(asgClient, ActiveAsg.get(AutoScalingGroupName), StandByAsg.get(AutoScalingGroupName))
                    isDeploy = True
        elif aSize:
            modifyAsg(asgClient, StandByAsg.get(AutoScalingGroupName), ActiveAsg[AutoScalingGroupName])
        elif sSize:
            modifyAsg(asgClient, ActiveAsg.get(AutoScalingGroupName), StandByAsg[AutoScalingGroupName])
            isDeploy = True
        return errorHandlingSuccess(isDeploy,msgTitle,msgContent)
    except:
        traceback.print_exc()
        return errorHandlingFailed(msgTitle,msgContent)
