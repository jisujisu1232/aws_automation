# Author: Jisu Kim
# Date created: 2018/07/05
# Date last modified: 2018/09/06
# Python Version: 2.7
'''
Precondition
    Create a topic and add this lambda to the topic

timeout : 5min 0sec

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
import json
import traceback
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
    TargetGroupARNs = 'TargetGroupARNs'
    Repetitions = 'repetitions'
    topicArn = None
    numberOfRepetitions = 2
    errorLambdaName = None

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

    #Call lambda with step and AutoScalingGroupName
    def callNextStep(asgName,step):
        nowStep = event.get('Step')
        if not nowStep:
            nowStep = 0
        if step == nowStep:
            print 'Can not call same Step : '+str(event.get('Step'))
            return False
        elif nowStep > step:
            print 'Can not call lower Step NOW : '+str(event.get('Step'))+' Call : '+str(step)
            return False
        lambdaClient = boto3.client('lambda')
        payload = {}
        payload['asgName']=asgName
        payload['Step']=step
        response = lambdaClient.invoke(
            FunctionName=context.function_name,
            InvocationType='Event',
            Payload=json.dumps(payload),
            Qualifier=context.function_version,
        )
        return response

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

    def deploySuccess(task):
        msg = '[Success] Non-disruptive deployment(Task : '+task+')'
        if errorLambdaName:
            callErrorHandling(task,False, False, False)
        else:
            sendMessageToAdmin(msg, msg)
        return responseReturn({'message': '[Success] Non-disruptive deployment'}, 200)

    def deployFailed(message, task):
        print message
        if not task:
            task = 'None'
        msgTitle = '[Failed] Non-disruptive deployment(errCode : '+message.get('errCode')+', Task : '+task+')'
        msgContent = message.get('errMessage')
        if errorLambdaName:
            callErrorHandling(task,message.get('errCode'), msgTitle, msgContent)
        else:
            sendMessageToAdmin(msgTitle, msgContent)
        return responseReturn(message, 400)
    def getTargetGroupNameFromArn(tgArn):
        return getNameFromArn(tgArn, 1)
    def getLBNameFromArn(lbArn):
        return getNameFromArn(lbArn, 2)
    def getNameFromArn(arn, i):
        return (arn.split(':')[5]).split('/')[i]
    def makeErrCode(step, errCode):
        if step>90:
            errCode+='-1'
        else:
            errCode+='-2'
        return errCode

    currentTask = None
    #Step and asgName in event are not exist when first call
    try:
        asgClient = boto3.client('autoscaling')

        Step = event.get('Step')
        if not Step:
            Step = 0
        calledASGName=event.get('asgName')
        if not calledASGName:
            #get ASG name when called by launch notification in ASG
            msgDict=json.loads(event['Records'][0]['Sns']['Message'])
            if msgDict.get('Event')=='autoscaling:TEST_NOTIFICATION':
                calledASGName = msgDict[AutoScalingGroupName]
            else:
                msg = '[PASS] is not autoscaling:TEST_NOTIFICATION'
                print msg
                return responseReturn({'message': msg}, 200)
        print calledASGName
        ldArn = context.invoked_function_arn
        resourceArn = ldArn[:ldArn.rfind(':')]
        if resourceArn.endswith(':function'):
            resourceArn = ldArn
        lambdaClient = boto3.client('lambda')
        topicArn = os.environ['topicArn']
        errorLambdaName = os.environ['errorLambdaName']
        triggerTopicArn = os.environ['triggerTopicArn']
        response = asgClient.describe_auto_scaling_groups(
            AutoScalingGroupNames = [calledASGName]
        )
        StandByAsg = tagsInASG(response.get('AutoScalingGroups')[0])
        currentTask = StandByAsg.get(Task)
        if StandByAsg.get(Type) == typeActive:
            msg = 'This ASG is Active ASG'
            print msg
            return responseReturn({'message': msg}, 200)
        desire = StandByAsg.get(DesiredCapacity)

        #One cycle takes about 3 minutes and 30 seconds
        #if numberOfRepetitions=2 then each step takes about 3 minutes and 30 seconds * 2
        repetitionsInASG = StandByAsg.get(Repetitions)
        if repetitionsInASG and len(repetitionsInASG)==1 and repetitionsInASG in '3456789':
            numberOfRepetitions = int(repetitionsInASG)
        print 'Step repetitions : '+ str(numberOfRepetitions)
        #When deployment start StandBy's desire is 1
        #The lambda has Step in event when the next process is going on.
        if desire == 0 or Step:
            ActiveAsg = False
            rsp = asgClient.describe_auto_scaling_groups()

            for asg in rsp['AutoScalingGroups']:
                tags = tagsInASG(asg)
                if tags.get(Task) == currentTask and tags.get(Type)==typeActive:
                    ActiveAsg = tags
                if ActiveAsg:
                    break

            if ActiveAsg:
                try:
                    elbClient = boto3.client('elb')
                    elbV2Client = boto3.client('elbv2')
                    activeInstances = []
                    if not ActiveAsg.get(LoadBalancerNames) and not ActiveAsg.get(TargetGroupARNs):
                        errMessage = ActiveAsg[AutoScalingGroupName] +'(Active) is not attach to ELB and Target Group'
                        errCode = 'T000'
                        raise KnownException(errCode, errMessage)

                    activeELBNames = ActiveAsg.get(LoadBalancerNames)
                    if not activeELBNames:
                        activeELBNames = []
                    activeTGArns = ActiveAsg.get(TargetGroupARNs)
                    if not activeTGArns:
                        activeTGArns = []
                    testELBNames = StandByAsg.get(LoadBalancerNames)
                    if not testELBNames:
                        testELBNames = []
                    testTGArns = StandByAsg.get(TargetGroupARNs)
                    if not testTGArns:
                        testTGArns = []

                    if not testTGArns and not testELBNames:
                        return responseReturn({'message': 'PASS'}, 200)

                    #LB and TG names in StandBy must start with tempPrefix when Step <= number of repetitions
                    #LB and TG names in StandBy must not start with tempPrefix when Step > number of repetitions
                    for testTGArn in testTGArns:
                        if getTargetGroupNameFromArn(testTGArn).startswith(tempPrefix):
                            if Step>numberOfRepetitions and Step<91:
                                return responseReturn({'message': 'PASS'}, 200)
                        else:
                            if Step<numberOfRepetitions+1 or Step>90:
                                return responseReturn({'message': 'PASS'}, 200)
                    for testELBName in testELBNames:
                        if testELBName.startswith(tempPrefix):
                            if Step>numberOfRepetitions and Step<91:
                                return responseReturn({'message': 'PASS'}, 200)
                        else:
                            if Step<numberOfRepetitions+1 or Step>90:
                                return responseReturn({'message': 'PASS'}, 200)

                    #LB and TG names in Active must not start with tempPrefix
                    for activeTGArn in activeTGArns:
                        if getTargetGroupNameFromArn(activeTGArn).startswith(tempPrefix):
                            return responseReturn({'message': 'PASS'}, 200)
                    for activeELBName in activeELBNames:
                        if activeELBName.startswith(tempPrefix):
                            return responseReturn({'message': 'PASS'}, 200)




                    '''
                    For Non-disruptive deployment
                    '''

                    '''
                    Start Step 1-{n}
                    Check StandBy ASG as a dummy LB and target group
                    '''
                    if Step <numberOfRepetitions:
                        stepCalledCnt=Step+1
                        subStepStr = str(stepCalledCnt)
                        print 'Step : 1-'+subStepStr+'('+currentTask+')'
                        #On the first call, modify StandBy's DesiredCapacity and MinSize to the value of Active's
                        if not Step:
                            if triggerTopicArn:
                                response = asgClient.delete_notification_configuration(
                                    AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                                    TopicARN=triggerTopicArn
                                )
                            response = asgClient.update_auto_scaling_group(
                                AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                                MinSize=ActiveAsg.get(MinSize),
                                MaxSize=ActiveAsg.get(MaxSize),
                                DesiredCapacity=ActiveAsg.get(DesiredCapacity)
                            )
                        sendMessageToAdmin('[Deploy] Call Step 1-'+subStepStr+'(Task : '+currentTask+')', 'Call Step 1-'+subStepStr+'(Task : '+currentTask+')')
                        isInServiceELB = []
                        isHealthyTG = []
                        for i in range(len(testELBNames)):
                            isInServiceELB.append(False)
                        for i in range(len(testTGArns)):
                            isHealthyTG.append(False)
                        isPass = True
                        #Check the dummy CLB and the target group for approximately 3 minutes and 30 seconds for each of the 0 and 1 Step
                        for i in range(42):
                            print 'Check in Test '+str(i)+'times'
                            for index, testELBName in enumerate(testELBNames):
                                if isInServiceELB[index]:
                                    continue
                                try:
                                    instancesInELB = elbClient.describe_instance_health(
                                        LoadBalancerName=testELBName
                                    )
                                except:
                                    callNextStep(calledASGName,92)
                                    return responseReturn({'message': 'Call Step 92'}, 400)
                                for i in instancesInELB['InstanceStates']:
                                    if i['State'].lower()=='inservice':
                                        isInServiceELB[index] = True
                                        print 'Success : Check InService in ' + testELBNames[index]
                                        break

                            for index, testTGArn in enumerate(testTGArns):
                                if isHealthyTG[index]:
                                    continue
                                try:
                                    instancesInTG = elbV2Client.describe_target_health(
                                        TargetGroupArn=testTGArn
                                    )
                                except:
                                    callNextStep(calledASGName,92)
                                    return responseReturn({'message': 'Call Step 92'}, 400)
                                for i in instancesInTG['TargetHealthDescriptions']:
                                    if i['TargetHealth']['State'].lower()=='healthy':
                                        isHealthyTG[index] = True
                                        print 'Success : Check Healthy in ' + getTargetGroupNameFromArn(testTGArns[index])
                                        break
                            isPass = True
                            for b in isInServiceELB:
                                if not b:
                                    isPass = False
                                    break
                            for b in isHealthyTG:
                                if not b:
                                    isPass = False
                                    break
                            if isPass:
                                break
                            sleep(5)
                        errorCLBs = []
                        errorTGs = []
                        isAllPass = True
                        for i, b in enumerate(isInServiceELB):
                            isPass = True
                            if b:
                                print 'Success : Check InService in ' + testELBNames[i]
                            else:
                                errorCLBs.append(testELBNames[i])
                                isAllPass = False
                                isPass = False
                                print 'Failed : Check InService in ' + testELBNames[i]
                        for i, b in enumerate(isHealthyTG):
                            tempTGArn=getTargetGroupNameFromArn(testTGArns[i])
                            isPass = True
                            if b:
                                print 'Success : Check Healthy in ' + tempTGArn
                            else:
                                errorTGs.append(tempTGArn)
                                isAllPass = False
                                isPass = False
                                print 'Failed : Check Healthy in ' + tempTGArn
                        if isAllPass:
                            callNextStep(calledASGName,numberOfRepetitions)
                            return responseReturn({'message': '[Success] Test Success on dummy LB and Target Group. And call Step 2'}, 200)
                        else:
                            if Step==numberOfRepetitions-1:
                                callNextStep(calledASGName,91)
                                return responseReturn({'message': 'Call Step 91 for remove dummy'}, 200)
                            else:
                                callNextStep(calledASGName,Step+1)
                                return responseReturn({'message': 'Call Step 1-'+str(stepCalledCnt+1)}, 200)

                        '''
                        Step1-{n} End


                        Step2-{n}
                        when first call or problem in step 1(
                            Delete all dummy LB and Target Group
                            when first call
                                StandBy ASG attach to Real LB
                        )
                        if Status is InService or Healthy
                            detach from Active ASG
                            set Active desire/min/max to 0/0/0
                            change StandBy/Active
                        else
                            deploy fail
                            set StandBy desire/min/max to 0/0/0



                        Step 91~
                        For remove dummy when any problem in Step 1-{n}
                        '''
                    elif Step>=numberOfRepetitions:
                        stepCalledCnt=None
                        if Step<91:
                            stepCalledCnt=Step+1-numberOfRepetitions
                            subStepStr = str(stepCalledCnt)
                            print 'Step : 2-'+subStepStr+'('+currentTask+')'
                            sendMessageToAdmin('[Deploy] Call Step 2-'+subStepStr+'(Task : '+currentTask+')', 'Call Step 2-'+subStepStr+'(Task : '+currentTask+')')
                        if Step==numberOfRepetitions or Step>90:
                            if len(testELBNames)>0:
                                try:
                                    response = asgClient.detach_load_balancers(
                                        AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                                        LoadBalancerNames=testELBNames
                                    )
                                except:
                                    errMessage = 'An error occurred when detaching testCLB from '+ StandByAsg[AutoScalingGroupName]+'(StandBy).'
                                    errCode = makeErrCode(Step,'T002')
                                    print errMessage
                                    #raise KnownException(errCode, errMessage)

                                try:
                                    for testELBName in testELBNames:
                                        response = elbClient.delete_load_balancer(
                                            LoadBalancerName=testELBName
                                        )
                                except:
                                    errMessage = 'An error occurred when deleting testCLBs('+", ".join(testELBNames)+').'
                                    errCode = makeErrCode(Step,'T003')
                                    raise KnownException(errCode, errMessage)

                                try:
                                    if Step==numberOfRepetitions:
                                        response = asgClient.attach_load_balancers(
                                            AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                                            LoadBalancerNames=activeELBNames
                                        )
                                except:
                                    errMessage = 'An error occurred when attaching activeCLBs from '+ StandByAsg[AutoScalingGroupName]+'(StandBy).'
                                    errCode = makeErrCode(Step,'T004')
                                    raise KnownException(errCode, errMessage)

                            if len(testTGArns)>0:
                                attachedLBArns = []
                                response = elbV2Client.describe_target_groups(
                                    TargetGroupArns=testTGArns
                                )
                                for tg in response['TargetGroups']:
                                    for attachedLBArn in tg['LoadBalancerArns']:
                                        isInList = False
                                        for arnInList in attachedLBArns:
                                            if arnInList == attachedLBArn:
                                                isInList = True
                                                break
                                        if not isInList:
                                            attachedLBArns.append(attachedLBArn)
                                try:
                                    for attachedLBArn in attachedLBArns:
                                        if getLBNameFromArn(attachedLBArn).startswith(tempPrefix):
                                            response = elbV2Client.describe_listeners(
                                                LoadBalancerArn=attachedLBArn
                                            )

                                            for listner in response['Listeners']:
                                                response = elbV2Client.delete_listener(
                                                    ListenerArn=listner['ListenerArn']
                                                )
                                            response = elbV2Client.delete_load_balancer(
                                                LoadBalancerArn=attachedLBArn
                                            )
                                        else:
                                            print getLBNameFromArn(attachedLBArn)+" is not startswith "+tempPrefix
                                except:
                                    errMessage = 'An error occurred when deleting test ALBs or NLBs.'
                                    errCode = makeErrCode(Step,'T005')
                                    raise KnownException(errCode, errMessage)

                                try:
                                    response = asgClient.detach_load_balancer_target_groups(
                                        AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                                        TargetGroupARNs=testTGArns
                                    )
                                    for testTGArn in testTGArns:
                                        response = elbV2Client.delete_target_group(
                                            TargetGroupArn=testTGArn
                                        )
                                    if Step==numberOfRepetitions:
                                        response = asgClient.attach_load_balancer_target_groups(
                                            AutoScalingGroupName=StandByAsg[AutoScalingGroupName],
                                            TargetGroupARNs=activeTGArns
                                        )
                                except:
                                    errMessage = 'An error occurred when deleting test Target Groups.'
                                    errCode = makeErrCode(Step,'T006')
                                    raise KnownException(errCode, errMessage)
                            if Step>90:
                                response = asgClient.update_auto_scaling_group(
                                    AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                                    MinSize=0,
                                    MaxSize=0,
                                    DesiredCapacity=0,
                                )
                                if Step==91:
                                    errMessage = '[Failed] error in Application'
                                    errCode = 'T001'
                                    raise KnownException(errCode, errMessage)
                                elif Step==92:
                                    errMessage = 'Someone deleted dummy CLB or Target Group'
                                    errCode = 'T000'
                                    raise KnownException(errCode, errMessage)
                        isInStandByInstance = []
                        for i in range(len(activeELBNames)):
                            isInStandByInstance.append(False)

                        isInStandByInstanceTG = []
                        for i in range(len(activeTGArns)):
                            isInStandByInstanceTG.append(False)
                        try:
                            for i in range(42):
                                response = asgClient.describe_auto_scaling_groups(
                                    AutoScalingGroupNames = [StandByAsg.get(AutoScalingGroupName)]
                                )
                                standByInstances = []
                                for instance in response['AutoScalingGroups'][0]['Instances']:
                                    standByInstances.append(instance['InstanceId'])

                                print 'Check in Real '+str(i)+'times'
                                for index, activeELBName in enumerate(activeELBNames):
                                    if isInStandByInstance[index]:
                                        continue
                                    instancesInELB = elbClient.describe_instance_health(
                                        LoadBalancerName=activeELBName
                                    )
                                    inServiceCnt = 0
                                    for i in instancesInELB['InstanceStates']:
                                        if i['InstanceId'] in standByInstances:
                                            print '[PASSED '+activeELBName+'] : ' + i['InstanceId'] +' in StandByInstance'
                                            isInStandByInstance[index] = True
                                            break

                                for index, activeTGArn in enumerate(activeTGArns):
                                    if isInStandByInstanceTG[index]:
                                        continue
                                    instancesInTG = elbV2Client.describe_target_health(
                                        TargetGroupArn=activeTGArn
                                    )
                                    inHealthyCount = 0
                                    for i in instancesInTG['TargetHealthDescriptions']:
                                        if i['TargetHealth']['State'].lower()=='healthy':
                                            if i['Target']['Id'] in standByInstances:
                                                print '[PASSED '+getTargetGroupNameFromArn(activeTGArn)+'] : ' + i['Target']['Id'] +' in StandByInstance'
                                                isInStandByInstanceTG[index] = True
                                                break
                                isPass = True
                                for b in isInStandByInstance:
                                    if not b:
                                        isPass = False
                                        break
                                for b in isInStandByInstanceTG:
                                    if not b:
                                        isPass = False
                                        break
                                if isPass:
                                    break
                                sleep(5)
                        except:
                            errMessage = 'An error occurred when Check with real LB or TG from '+StandByAsg.get(AutoScalingGroupName)+'(StandBy) .'
                            errCode = 'T007'
                            raise KnownException(errCode, errMessage)

                        errorCLBs = []
                        errorTGs = []
                        isPass = True
                        for i, b in enumerate(isInStandByInstance):
                            if not isInStandByInstance[i]:
                                isPass = False
                                errorCLBs.append(activeELBNames[i])
                                print 'Failed : Non-disruptive deployment failed in '+activeELBNames[i]
                        for i, b in enumerate(isInStandByInstanceTG):
                            if not isInStandByInstanceTG[i]:
                                isPass = False
                                errorTGs.append(getTargetGroupNameFromArn(activeTGArns[i]))
                                print 'Failed : Non-disruptive deployment failed in '+getTargetGroupNameFromArn(activeTGArns[i])
                        if isPass:
                            try:
                                if len(activeELBNames)>0:
                                    response = asgClient.detach_load_balancers(
                                        AutoScalingGroupName=ActiveAsg[AutoScalingGroupName],
                                        LoadBalancerNames=activeELBNames
                                    )
                                if len(activeTGArns)>0:
                                    response = asgClient.detach_load_balancer_target_groups(
                                        AutoScalingGroupName=ActiveAsg[AutoScalingGroupName],
                                        TargetGroupARNs=activeTGArns
                                    )
                            except:
                                errMessage = 'An error occurred when detaching real CLBs and Target Groups from '+ActiveAsg.get(AutoScalingGroupName)+'(Active) .'
                                errCode = 'T008'
                                raise KnownException(errCode, errMessage)
                            try:
                                response = asgClient.update_auto_scaling_group(
                                    AutoScalingGroupName=ActiveAsg[AutoScalingGroupName],
                                    MinSize=0,
                                    MaxSize=0,
                                    DesiredCapacity=0,
                                )
                                if not responseCheck(response):
                                    raise Exception
                            except:
                                errMessage = ActiveAsg[AutoScalingGroupName]+'[Min, Max ,Desire] to 000 failed. you need to change Active ASG[Min, Max ,Desire] to 0 And swap Tag Type Active/StandBy'
                                errCode = 'T009'
                                raise KnownException(errCode, errMessage)

                            try:
                                response = asgClient.create_or_update_tags(
                                    Tags=[
                                        {
                                        'ResourceId':ActiveAsg[AutoScalingGroupName],
                                        'ResourceType': 'auto-scaling-group',
                                        'Key': Type,
                                        'Value': typeStandBy,
                                        'PropagateAtLaunch': False
                                        },
                                        {
                                        'ResourceId': StandByAsg.get(AutoScalingGroupName),
                                        'ResourceType': 'auto-scaling-group',
                                        'Key': Type,
                                        'Value': typeActive,
                                        'PropagateAtLaunch': False
                                        }
                                    ]
                                )
                                if not responseCheck(response):
                                    raise Exception
                            except:
                                try:
                                    response = asgClient.create_or_update_tags(
                                        Tags=[
                                            {
                                            'ResourceId':ActiveAsg[AutoScalingGroupName],
                                            'ResourceType': 'auto-scaling-group',
                                            'Key': Type,
                                            'Value': typeStandBy,
                                            'PropagateAtLaunch': False
                                            },
                                            {
                                            'ResourceId': StandByAsg.get(AutoScalingGroupName),
                                            'ResourceType': 'auto-scaling-group',
                                            'Key': Type,
                                            'Value': typeActive,
                                            'PropagateAtLaunch': False
                                            }
                                        ]
                                    )
                                    if not responseCheck(response):
                                        raise Exception
                                except:
                                    errMessage = 'Active/StandBy swap Failed. Please change tag('+Type+') '+ActiveAsg[AutoScalingGroupName]+' to '+typeStandBy+' and '+StandByAsg.get(AutoScalingGroupName)+' to '+typeActive
                                    errCode = 'T010'
                                    raise KnownException(errCode, errMessage)

                            print '[Success] Non-disruptive deployment'
                            return deploySuccess(currentTask)
                        else:
                            if Step<(numberOfRepetitions*2)-1:
                                callNextStep(calledASGName,Step+1)
                                return responseReturn({'message': 'Call Step 2-'+str(stepCalledCnt+1)}, 200)
                            else:
                                try:
                                    response = asgClient.update_auto_scaling_group(
                                        AutoScalingGroupName=StandByAsg.get(AutoScalingGroupName),
                                        MinSize=0,
                                        MaxSize=0,
                                        DesiredCapacity=0,
                                    )
                                    if not responseCheck(response):
                                        raise Exception
                                    errMessage = 'Test Failed on dummy '
                                    strErrCLBs=", ".join(errorCLBs)
                                    if strErrCLBs:
                                        errMessage+='CLB('+strErrCLBs+')'
                                    strErrorTGs=", ".join(errorTGs)
                                    if strErrorTGs:
                                        if strErrCLBs:
                                            errMessage+=' and '
                                        errMessage+='Target Group('+strErrorTGs+')'
                                    errCode = 'T011'
                                    raise KnownException(errCode, errMessage)
                                except KnownException, e:
                                    raise e
                                except:
                                    errMessage = 'Test Failed on dummy '
                                    strErrCLBs=", ".join(errorCLBs)
                                    if strErrCLBs:
                                        errMessage+='CLB('+strErrCLBs+')'
                                    strErrorTGs=", ".join(errorTGs)
                                    if strErrorTGs:
                                        if strErrCLBs:
                                            errMessage+=' and '
                                        errMessage+='Target Group('+strErrorTGs+')'
                                    errMessage+=' and Failed update '+StandByAsg.get(AutoScalingGroupName)+'(StandBy) DesiredCapacity/Min/Max to 0/0/0'
                                    errCode = 'T012'
                                    raise KnownException(errCode, errMessage)

                    '''
                    Step 2-{n} End
                    '''
                except KnownException, e:
                    message = {}
                    message['errCode']=e.args[0]
                    message['errMessage']=e.args[1]
                    return deployFailed(message, currentTask)
                except Exception, e:
                    traceback.print_exc()
                    message = {}
                    message['errCode']='UNKNOWN'
                    message['errMessage']='Unknown Err. Please Check CloudWatch log '+context.function_name
                    return deployFailed(message, currentTask)
            else:
                errMessage = "Has no Active/StandBy Autoscaling Group"
                errCode = 'T013'
                message = {}
                message['errCode']=errCode
                message['errMessage']=errMessage
                return deployFailed(message, currentTask)
        else:
            pass
        return responseReturn({'message': 'PASS'}, 200)
    except:
        traceback.print_exc()
        message = {}
        message['errCode']='UNKNOWN'
        message['errMessage']='Unknown Err. Please Check CloudWatch log '+context.function_name
        return deployFailed(message, currentTask)
