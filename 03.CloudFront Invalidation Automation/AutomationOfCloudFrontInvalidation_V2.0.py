# Author: Jisu Kim
# Date created: 2018/08/15
# Python Version: 2.7
'''
[CloudFront Invalidation Automation Lambda]

Precondition
    s3 buckets
        1. used in CloudFront ->Properties->Events-> ObjectCreate(All) and ObjectDelete(All) to This Lambda

        2. Bucket to store errors

    sqs
        Default Visibility Timeout  5min
        Message Retention Period    1min
        Maximum Message Size        256kb
        Delivery Delay              0

    sns
        topic has admin's email for send error

s3 bucket tag
key             Value
exceptionPaths  Exception paths when eventName is not 'ObjectRemoved:Delete'
                separator -> ','
                ex) resources/upload/*,resources/test/*



timeout : 5min 0sec
tag in this lambda
[Key]           [Value]
topicArn        Default {snsTopicArn in admin's email}
errorBucket     {save err paths}
qUrl            sqs url for send and receive

iam role
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetBucketTagging",
                "sns:Publish",
                "lambda:TagResource",
                "lambda:InvokeFunction",
                "lambda:ListTags",
                "sqs:ReceiveMessage",
                "sqs:SendMessage",
                "cloudfront:ListDistributions",
                "cloudfront:CreateInvalidation"
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
import string
import random
import traceback
import time

from datetime import datetime

def lambda_handler(event, context):
    class PassException(Exception):
        pass
    startTime = time.time()
    def findAll(str, substr):
        returnArr = []
        currIdx = 0
        while True:
            subidx = str[currIdx:].find(substr)
            if subidx==-1:
                break
            else:
                currIdx += subidx+1
                returnArr.append(currIdx-1)
        return returnArr
    def behaviorPathCheck(behaviorPath, key):
        if behaviorPath.startswith('/'):
            behaviorPath = behaviorPath[1:]
        asteriskIdxArr = findAll(behaviorPath,'*')
        arrSize = len(asteriskIdxArr)
        if arrSize == 0:
            if behaviorPath==key:
                return True
        else:
            isPass = True
            currIdx = -1
            for i in range(arrSize):
                prevIdx = currIdx
                currIdx = asteriskIdxArr[i]
                findStr = behaviorPath[prevIdx+1:currIdx]
                if prevIdx == -1:
                    if not key.startswith(findStr):
                        isPass = False
                        break
                else:
                    keyIdx = key.find(findStr)
                    if keyIdx==-1:
                        isPass = False
                        break
                    else:
                        key = key[keyIdx+len(findStr):]
                        pass
            if isPass:
                if key.endswith(behaviorPath[currIdx+1:]):
                    return True
                else:
                    return False
        return False
    def getLambdaTags(lambdaClient, resourceArn):
        response = lambdaClient.list_tags(
            Resource=resourceArn
        )
        return response.get('Tags')

    def getOriginGroupIds(originGroups, originId):
        '''
            'Items': [
                {
                    'Id': 'string',
                    'FailoverCriteria': {
                        'StatusCodes': {
                            'Quantity': 123,
                            'Items': [
                                123,
                            ]
                        }
                    },
                    'Members': {
                        'Quantity': 123,
                        'Items': [
                            {
                                'OriginId': 'string'
                            },
                        ]
                    }
                },
            ]
        '''
        returnArr = []
        if originGroups:
            for originGroup in originGroups['Items']:
                for member in originGroup['Members']['Items']:
                    if member['OriginId'] == originId:
                        returnArr.append(originGroup['Id'])
        return returnArr
    isCallBack = False
    if event.get('callback'):
        isCallBack = True
        print 'CallBack'
    else:
        key = event['Records'][0]['s3']['object']['key']
        bucket = event['Records'][0]['s3']['bucket']['name']
        eventName = event['Records'][0]['eventName']
        print 'Key : '+key+' , bucket : '+bucket+' , eventName : '+eventName
    lambdaClient = boto3.client('lambda')
    ldArn = context.invoked_function_arn
    resourceArn = ldArn[:ldArn.rfind(':')]
    if resourceArn.endswith(':function'):
        resourceArn = ldArn
    lambdaTags = getLambdaTags(lambdaClient, resourceArn)
    queue_url = lambdaTags.get('qUrl')
    if not queue_url:
        print '[Failed] Must have tag name \'qUrl\' in Lambda'
        return
    s3Client = boto3.client('s3')
    sqsClient = boto3.client('sqs')
    if not isCallBack:
        response = s3Client.get_bucket_tagging(
            Bucket=bucket
        )
        exceptionPaths = None

        for tag in response['TagSet']:
            tagKey = tag['Key']
            if tagKey=='exceptionPaths':
                exceptionPaths = tag['Value']
        if exceptionPaths:
            ePathArr = exceptionPaths.split(',')
            for ePath in ePathArr:
                ePath = ePath.strip()
                if ePath:
                    if ePath[:1]!='*' and ePath[:1]!='/':
                        ePath = '/'+ePath
                    if ePath[-1:]!='*':
                        ePath=ePath+'*'
                    if eventName != 'ObjectRemoved:Delete':
                        if behaviorPathCheck(ePath, key):
                            print ePath+' is Exception Path'
                            return
        response = sqsClient.send_message(
            QueueUrl=queue_url,
            MessageBody=(
                '{"bucket":"'+bucket+'","key":"'+key+'","eventName":"'+eventName+'"}'
            )
        )
        currentCallTime = lambdaTags.get('currentCallTime')
        executeTime = datetime.now()
        isPass = True
        if currentCallTime:
            diffStr = str(executeTime - datetime.strptime(currentCallTime, '%Y%m%d%H%M%S'))
            if 'day' not in diffStr:
                sIdx = diffStr.rfind(':')
                startIdx = sIdx-5
                if startIdx <0:
                    startIdx = 0
                diffStr = diffStr[startIdx:sIdx+3].replace(':','')
                if  int(diffStr)< 11:
                    isPass = False
        if isPass:
            response = lambdaClient.tag_resource(
                Resource=resourceArn,
                Tags={
                    'currentCallTime': executeTime.strftime('%Y%m%d%H%M%S')
                }
            )
        else:
            print 'progress is already running.'
            return
        time.sleep(5)
    saveDict = {}
    bucketList = []
    cfList = []
    keysInCFsList = []
    keyEventDict = {}
    while True:
        try:
            if (time.time() - startTime) > 240:
                payload = {}
                payload['callback']='True'
                response = lambdaClient.invoke(
                    FunctionName=context.function_name,
                    InvocationType='Event',
                    Payload=json.dumps(payload),
                    Qualifier=context.function_version,
                )
                break
            response = sqsClient.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                VisibilityTimeout=3600,
                WaitTimeSeconds=8,
            )

            messages = response.get('Messages')

            if messages:
                for message in messages:
                    body = message.get('Body')
                    if not body:
                        continue
                    body = json.loads(body)

                    bucket = body.get('bucket')
                    if not saveDict.get(bucket):
                        saveDict.update({bucket:[]})
                        bucketList.append(bucket)
                    key = body.get('key')
                    eventName = body.get('eventName')
                    keyEventDict.update({key:eventName})
                    if key not in saveDict.get(bucket):
                        saveDict.get(bucket).append(key)
                if len(messages)==0:
                    break
            else:
                break
        except:
            traceback.print_exc()
            break
    if bucketList:
        cfClient = boto3.client('cloudfront')
        response = cfClient.list_distributions()
        cfIds = []
        for cf in response['DistributionList']['Items']:
            for origin in cf['Origins']['Items']:
                for index, bucket in enumerate(bucketList):
                    if origin['DomainName'] == (bucket+'.s3.amazonaws.com'):
                        originGroupIds = getOriginGroupIds(cf.get('OriginGroups'), origin['Id'])
                        for behavior in cf['CacheBehaviors']['Items']:
                            for key in saveDict.get(bucket):
                                if behaviorPathCheck(behavior['PathPattern'],key):
                                    if origin['Id'] == behavior['TargetOriginId'] or behavior['TargetOriginId'] in originGroupIds:
                                        isAdd = False
                                        if behavior['MaxTTL']>0:
                                            isAdd = True
                                        elif keyEventDict.get(key) == 'ObjectRemoved:Delete':
                                            isAdd = True
                                        if isAdd:
                                            if cf['Id'] not in cfList:
                                                cfList.append(cf['Id'])
                                                keysInCFsList.append([])
                                            key = '/'+key
                                            if key not in keysInCFsList[cfList.index(cf['Id'])]:
                                                keysInCFsList[cfList.index(cf['Id'])].append(key)
                                    else:
                                        continue
        choice = string.ascii_lowercase+'0123456789'
        maxInvalidationPathSize = 3000
        errorList = []
        isInError = False
        for cfId in cfList:
            try:
                errorList.append([cfId])
                allInvalidationPaths = keysInCFsList[cfList.index(cfId)]
                if allInvalidationPaths:
                    cfInvalidationsList=[]
                    for i in range((len(allInvalidationPaths)/maxInvalidationPathSize)+1):
                        if i==0:
                            cfInvalidationsList.append(allInvalidationPaths[:maxInvalidationPathSize])
                        elif maxInvalidationPathSize*i < len(allInvalidationPaths):
                            cfInvalidationsList.append(allInvalidationPaths[maxInvalidationPathSize*i:maxInvalidationPathSize*(i+1)])
                        else:
                            break
                    for cfInvalidations in cfInvalidationsList:
                        callerRef = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:-3]
                        for i in range(10):
                            callerRef += random.choice(choice)
                        try:
                            response = cfClient.create_invalidation(
                                DistributionId=cfId,
                                InvalidationBatch={
                                    'Paths': {
                                        'Quantity': len(cfInvalidations),
                                        'Items': cfInvalidations
                                    },
                                    'CallerReference':callerRef
                                }
                            )
                        except:
                            traceback.print_exc()
                            errorList[len(errorList)-1].append(cfInvalidations)
                            isInError = True
                print '[End]'+cfId
            except:
                print 'error in : ' + cfId
                traceback.print_exc()
        if isInError:
            if lambdaTags.get('errorBucket'):
                errTxtKey = datetime.now().strftime('%Y%m%d%H%M%S%f')
                for i in range(10):
                    errTxtKey += random.choice(choice)
                errTxtKey = 'invalidation_error/'+errTxtKey+'_'
                errKeyList = []
                for cfErr in errorList:
                    body = ''
                    if len(cfErr)==1:
                        continue
                    for i, paths in enumerate(cfErr):
                        if i==0:
                            body+='CloudFront Id ['+paths+']\n'
                        else:
                            body+='(Set '+str(i)+' Start)\n\n'
                            for path in paths:
                                body+=path+'\n'
                            body+='\n(Set '+str(i)+' End)\n\n'
                    objKey = errTxtKey+cfErr[0]+'.txt'
                    errKeyList.append(objKey)
                    s3Client.put_object(
                        Bucket=lambdaTags.get('errorBucket'),
                        Key=objKey,
                        Body=body
                    )
                if lambdaTags.get('topicArn'):
                    message = 'bucket : '+lambdaTags.get('errorBucket')+'\n\n'
                    for errKey in errKeyList:
                        message+=errKey+'\n'
                    snsClient = boto3.client("sns")
                    response = snsClient.publish(
                        Subject = '[Error] CloudFront Invalidation',
                        TopicArn = lambdaTags.get('topicArn'),
                        Message = message
                    )
