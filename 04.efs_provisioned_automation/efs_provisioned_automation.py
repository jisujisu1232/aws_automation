# Author: Jisu Kim
# Date created: 2019/07/30
# Python Version: 2.7
'''
[EFS Provisioned Automation Lambda]

Precondition
    EFS

    sns
        1. SNS topic with lambda
        2. SNS topic with admin emails

    CloudWatch Alarm
        EFS's BurstCreditBalance



timeout : 5min 0sec

tags in lambda
[Key]           [Value]
mibps           {Provisioned Throughput In Mibps}
adminSNSArn     {admin SNS Topic Arn}

iam role
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "sns:Publish",
                "lambda:TagResource",
                "lambda:ListTags",
                "elasticfilesystem:UpdateFileSystem",
                "elasticfilesystem:DescribeFileSystems",
                "events:DeleteRule",
                "events:PutTargets",
                "events:DescribeRule",
                "events:EnableRule",
                "events:RemoveTargets",
                "events:ListTargetsByRule",
                "events:DisableRule",
                "events:PutRule",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:CreateLogGroup"
            ],
            "Resource": "*"
        }
    ]
}
'''
import json
import boto3
import datetime
import traceback
import random
import string
import botocore

def lambda_handler(event, context):
    '''
    {
        u'Records': [
            {
                u'EventVersion': u'1.0',
                u'EventSubscriptionArn': u'arn:aws:s1234',
                u'EventSource': u'aws:sns',
                u'Sns': {
                    u'SignatureVersion': u'1',
                    u'Timestamp': u'2019-07-30T01:41:26.940Z',
                    u'Signature': u'==',
                    u'SigningCertUrl': u'https://sns.ap-northeast-2.amazonaws.com/3f9.pem',
                    u'MessageId': u'asdf',
                    u'Message': u'{
                        "AlarmName":"asdf",
                        "AlarmDescription":"asdf",
                        "AWSAccountId":"12321",
                        "NewStateValue":"ALARM",
                        "NewStateReason":"Threshold Crossed:",
                        "StateChangeTime":"2019-07-30T01:41:26.905+0000",
                        "Region":"Asia Pacific (Seoul)",
                        "OldStateValue":"OK",
                        "Trigger":{
                            "MetricName":"BurstCreditBalance",
                            "Namespace":"AWS/EFS",
                            "StatisticType":"Statistic",
                            "Statistic":"MINIMUM",
                            "Unit":null,
                            "Dimensions":[
                                {
                                    "value":"fs-",
                                    "name":"FileSystemId"
                                }
                            ],
                            "Period":60,
                            "EvaluationPeriods":1,
                            "ComparisonOperator":"LessThanOrEqualToThreshold",
                            "Threshold":2.400000000001E12,
                            "TreatMissingData":"",
                            "EvaluateLowSampleCountPercentile":""
                        }
                    }',
                    u'MessageAttributes': {},
                    u'Type': u'Notification',
                    u'UnsubscribeUrl': u'https://sns.ap-northeast-2.amazonaws.com/?Action=Unsubscribe',
                    u'TopicArn': u'arn:est-seoul',
                    u'Subject': u'ALARM: "adf" in Asia Pacific (Seoul)'
                }
            }
        ]
    }
    '''
    class KnownException(Exception):
        def __init__(self, *args):
            self.args = [a for a in args]

    def getLambdaTags(lambdaClient, resourceArn):
        response = lambdaClient.list_tags(
            Resource=resourceArn
        )
        return response.get('Tags')

    def makeTempName(tempPrefix):
        tempName = tempPrefix
        for i in range(20):
            tempName += random.choice(string.ascii_lowercase)
        return tempName


    def responseCheck(response):
        try:
            if response.get('ResponseMetadata').get('HTTPStatusCode')!=200:
                print response.get('ResponseMetadata')
                return False
        except:
            return False
        return True

    def sendMessageToAdmin(subject, message, topicArn):
        try:
            print subject
            print message
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

    efsClient=boto3.client("efs")

    ldArn = context.invoked_function_arn
    resourceArn = ldArn[:ldArn.rfind(':')]
    lambdaClient=boto3.client("lambda")
    if resourceArn.endswith(':function'):
        resourceArn = ldArn

    lambdaTags = getLambdaTags(lambdaClient, resourceArn)

    adminTopic=lambdaTags.get('adminSNSArn')

    provisionedThroughputInMibps = lambdaTags.get('mibps')

    mode='bursting'
    if event.get('manual'):
        mode='provisioned'

    efsId=event.get('efsId')
    ruleName=event.get('ruleName')
    efsName='None'
    efsUpdateArgs={}
    if not efsId:
        paramJsonStr=event['Records'][0]['Sns']['Message']
        if event.get('test'):
            '''
            {
                "test":"true",
                "Records": [
                    {
                        "Sns": {
                            "Message": "{'Trigger':{'Dimensions':[{'value':'{AWS EFS Id}','name':'FileSystemId'}]}}"
                        }
                    }
                ]
            }
            '''
            paramJsonStr=paramJsonStr.replace("'",'"')
        snsMessage=json.loads(paramJsonStr)
        efsId=snsMessage.get('Trigger').get('Dimensions')[0].get('value')
        mode='provisioned'

    try:
        isSameMode=False
        response = efsClient.describe_file_systems(
            FileSystemId=efsId
        )
        efsInfo=response.get('FileSystems')[0]
        if mode==efsInfo.get('ThroughputMode'):
            isSameMode=True
        if efsInfo.get('Name'):
            efsName=efsInfo.get('Name')
        if mode=='provisioned':
            if not provisionedThroughputInMibps:
                provisionedThroughputInMibps=''
            provisionedThroughputInMibps=provisionedThroughputInMibps.replace(' ','')
            if provisionedThroughputInMibps.isdigit():
                efsUpdateArgs.update({'ProvisionedThroughputInMibps':int(provisionedThroughputInMibps)})
            else:
                raise KnownException('E000', efsName+'('+efsId+')','Lambda '+context.function_name+'\'s tag mibps is not a number.')

        efsUpdateArgs.update({'FileSystemId':efsId})
        efsUpdateArgs.update({'ThroughputMode':mode})
        eventsClient = boto3.client('events')
        try:
            if not isSameMode:
                try:
                    efsClient.update_file_system(**efsUpdateArgs)
                except botocore.exceptions.ClientError, e:
                    traceback.print_exc()
                    errResponse=e.response
                    if errResponse.get('Error').get('Code')=='TooManyRequests':
                        #You have reached the maximum number of throughput mode changes or provisioned throughput value decreases. Wait until 2019-07-31T08:37:26Z UTC and try again.
                        errMessage=errResponse.get('Error').get('Message')
                        if not ruleName:
                            raise KnownException('E001',efsName+'('+efsId+')', errMessage)
                        #2019-07-31T08:37:26Z
                        print errMessage.split('until ')[1].split(' UTC')[0]
                        cronDate=datetime.datetime.strptime(errMessage.split('until ')[1].split(' UTC')[0],'%Y-%m-%dT%H:%M:%SZ')+datetime.timedelta(minutes=2)
                        if cronDate<datetime.datetime.today():
                            cronDate=datetime.datetime.today()+datetime.timedelta(minutes=2)
                        response = eventsClient.put_rule(
                            Name=ruleName,
                            ScheduleExpression='cron('+str(cronDate.minute)+' '+str(cronDate.hour)+' '+str(cronDate.day)+' * ? *'+')'
                        )
                        sendMessageToAdmin('[EFS Automation Alarm]'+efsName+'('+efsId+')', str(cronDate)+' UTC, throughput mode of '+efsName+'('+efsId+')'+' will be changed to '+mode, adminTopic)
                        return
                    else:
                        raise e
            else:
                print 'mode same'
        except KnownException, e:
            raise e
        except:
            traceback.print_exc()
            errMsg='Failed to update '+efsName+'('+efsId+')\'s throughput mode to '+mode
            if mode=='provisioned':
                raise KnownException('E001',efsName+'('+efsId+')', errMsg)
            else:
                raise KnownException('E002',efsName+'('+efsId+')', errMsg)

        if mode=='provisioned':

            ruleName=makeTempName('efsBurstingMadeByLambda-')
            for i in range(100):
                try:
                    describeRule = eventsClient.describe_rule(
                        Name=ruleName
                    )
                    ruleName=makeTempName('efsBurstingMadeByLambda-')
                except:
                    break
            cronDate = datetime.datetime.today()+datetime.timedelta(days=1,minutes=1)

            targetName=makeTempName('efsBurstingLambda-')
            try:
                response = eventsClient.put_rule(
                    Name=ruleName,
                    ScheduleExpression='cron('+str(cronDate.minute)+' '+str(cronDate.hour)+' '+str(cronDate.day)+' * ? *'+')',
                    State='DISABLED',
                    Description='Made By Lambda for '+efsId
                )
                ruleArn=response.get('RuleArn')
                ruleName=ruleArn.split('/')[1]

                response = eventsClient.put_targets(
                    Rule=ruleName,
                    Targets=[
                        {
                            'Id': targetName,
                            'Arn': resourceArn,
                            'Input': '{"efsId":"'+efsId+'","ruleName":"'+ruleName+'"}',
                        },
                    ]
                )

                if response.get('FailedEntries'):
                    response = eventsClient.delete_rule(
                        Name=ruleName
                    )
                    raise Exception
                else:
                    response = eventsClient.enable_rule(
                        Name=ruleName
                    )
            except:
                traceback.print_exc()
                raise KnownException('E003', efsName+'('+efsId+')','Failed to set CloudWatch rule('+ruleName+').')

        else:
            eventsClient.disable_rule(
                Name=ruleName
            )

            targetResponse = eventsClient.list_targets_by_rule(
                Rule=ruleName
            )

            targetIds=[target.get("Id") for target in targetResponse.get('Targets')]
            try:
                response = eventsClient.remove_targets(
                    Rule=ruleName,
                    Ids=targetIds
                )

                response = eventsClient.delete_rule(
                    Name=ruleName
                )
            except:
                traceback.print_exc()
                raise KnownException('E004', efsName+'('+efsId+')','Failed to delete CloudWatch rule('+ruleName+').')
        snsMessage='Successful update of '+efsName+'('+efsId+')\'s throughput mode to '+mode
        sendMessageToAdmin('[Success EFS Automation]'+efsName+'('+efsId+')', snsMessage, adminTopic)
    except KnownException, e:
        traceback.print_exc()
        sendMessageToAdmin('[Failed EFS Automation]'+'['+e.args[0]+']'+e.args[1], '['+e.args[1]+']\n'+e.args[2], adminTopic)
    except:
        traceback.print_exc()
        errMsg='[Unknown Error]'+efsName+'('+efsId+')'
        sendMessageToAdmin('[Failed EFS Automation]'+errMsg, errMsg, adminTopic)
