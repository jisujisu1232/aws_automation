#!/bin/bash
#
# bastion Bootstrapping
# authors: tonynv@amazon.com, sancard@amazon.com, ianhill@amazon.com
# NOTE: This requires GNU getopt. On Mac OS X and FreeBSD you must install GNU getopt and mod the checkos function so that it's supported
#
# Modified by Jisu Kim

## Configuration
PROGRAM='Init'

##################################### Functions Definitions


if [ $# == 0 ] ; then echo "No input provided!        $0 {CWLogGroup} {logFile}" >&2 ; exit 1 ; fi

CLOUDWATCHGROUP=$1

LOG_FILE_PATH=$2

REGION=$(curl -sq http://169.254.169.254/latest/meta-data/placement/availability-zone/)

REGION=${REGION: :-1}

function osrelease () {
    OS=`cat /etc/os-release | grep '^NAME=' |  tr -d \" | sed 's/\n//g' | sed 's/NAME=//g'`
    if [ "${OS}" == "Ubuntu" ]; then
        echo "Ubuntu"
    elif [ "${OS}" == "Amazon Linux AMI" ]; then
        echo "AMZN"
    elif [ "${OS}" == "Amazon Linux" ]; then
        echo "AMZN2"
    elif [ "${OS}" == "CentOS Linux" ]; then
        echo "CentOS"
    else
        echo "Operating System Not Found"
    fi
}

function setup_environment_variables() {

  ETH0_MAC=$(/sbin/ip link show dev eth0 | /bin/egrep -o -i 'link/ether\ ([0-9a-z]{2}:){5}[0-9a-z]{2}' | /bin/sed -e 's,link/ether\ ,,g')

  _userdata_file="/var/lib/cloud/instance/user-data.txt"

  INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)

  LOCAL_IP_ADDRESS=$(curl -sq 169.254.169.254/latest/meta-data/network/interfaces/macs/${ETH0_MAC}/local-ipv4s/)

  CWG=${CLOUDWATCHGROUP}


  # LOGGING CONFIGURATION
  BASTION_MNT="/var/log/bastion"
  BASTIONLOG="bastion.log"
  BASTION_LOGFILE="${BASTION_MNT}/${BASTIONLOG}"
  BASTION_LOGFILE_SHADOW="${BASTION_MNT}/.${BASTIONLOG}"
  log_shadow_file_location="${bastion_mnt}/.${BASTIONLOG}"
  echo "Setting up bastion session log in ${BASTION_MNT}/${BASTIONLOG}"
  if [ ! -f "$BASTION_LOGFILE" ] ; then
	  mkdir -p ${BASTION_MNT}
	  touch ${BASTION_LOGFILE}
	  ln ${BASTION_LOGFILE} ${BASTION_LOGFILE_SHADOW}
	  mkdir -p /usr/bin/bastion
	  touch /tmp/messages
	  chmod 770 /tmp/messages
  fi

  if [ "${release}" == "Ubuntu" ]; then
  	#Call function for Ubuntu
  	echo "Ubuntu pass"
  else

  	grepStr2=$(grep "Added by Shell Script" "/etc/sudoers")
    grepLength2=${#grepStr2}

  	if [ $grepLength2 -le 0 ] ; then
  		echo -e "#Added by Shell Script" >>/etc/sudoers
  		echo -e "\nDefaults env_keep += \"SSH_CLIENT\"" >>/etc/sudoers
  	fi
  	echo "/etc/sudoers set"
  	grepStr3=$(grep "Added by Shell Script" "/etc/bashrc")
    grepLength3=${#grepStr3}

    if [ $grepLength3 -le 0 ] ; then

cat <<'EOF' >> /etc/bashrc
#Added by Shell Script
declare -rx IP=$(echo $SSH_CLIENT | awk '{print $1}')
EOF

      echo "declare -rx BASTION_LOG=${BASTION_MNT}/${BASTIONLOG}" >> /etc/bashrc

cat <<'EOF' >> /etc/bashrc
declare -rx PROMPT_COMMAND='history -a >(logger -t "ON: $(date)   [FROM]:${IP}   [USER]:${USER}   [PWD]:${PWD}" -s 2>>${BASTION_LOG})'
EOF

  	fi
  	echo "/etc/bashrc set"
  fi


	cat /dev/null > ~/cloudwatchlog.conf
	cat /dev/null > ~/cloudwatchSSHLog.conf
  cat /dev/null > ~/awslogs_logging.conf

	cat /dev/null > /tmp/filename.txt
	cat /dev/null > /tmp/groupname.txt
	cat /dev/null > ~/cwLogGroup.txt
	echo "file = ${BASTION_LOGFILE_SHADOW}" >> /tmp/filename.txt
	echo "log_group_name = ${CWG}" >> /tmp/groupname.txt


  export ETHO_MAC CWG BASTION_MNT BASTIONLOG BASTION_LOGFILE BASTION_LOGFILE_SHADOW \
          LOCAL_IP_ADDRESS INSTANCE_ID
}

function verify_dependencies(){
  pathStr="$PATH"
  if [[ $pathStr != */usr/local/bin* ]]; then
     export PATH=$PATH:/usr/local/bin
  fi
  which pip &> /dev/null
  if [ $? -ne 0 ] ; then
      echo "PIP NOT INSTALLED"
      [ `which yum` ] && $(yum install -y epel-release; yum install -y python-pip) && echo "PIP INSTALLED"
      [ `which apt-get` ] && apt-get -y update && apt-get -y install python-pip && echo "PIP INSTALLED"
      [ `which apt` ] && apt -y update && apt -y install python-pip && echo "PIP INSTALLED"
      pip install --upgrade pip &> /dev/null
  fi
  pip install awscli --ignore-installed six &> /dev/null

  if [ $? -ne 0 ] ; then
    pip install --upgrade pip &> /dev/null
    pip install awscli --ignore-installed six &> /dev/null
  fi

	echo $(aws logs describe-log-groups --region ${REGION} --log-group-name-prefix ${CLOUDWATCHGROUP}) > ~/cwLogGroup.txt
	awk '/\"'+${CLOUDWATCHGROUP}+'\"/' ~/cwLogGroup.txt > ~/logCliResponse.txt
	responseStr=$(awk '/{/' logCliResponse.txt)


	if [ ${#responseStr} == 0 ] ; then
			echo "CloudWatch Log Group does not exist.."
			exit 1
	fi
  echo "${FUNCNAME[0]} Ended"
}

function writeDefaultConf(){
cat <<'EOF' >> ~/awslogs_logging.conf
[loggers]
keys=root,cwlogs,reader,publisher

[handlers]
keys=consoleHandler

[formatters]
keys=simpleFormatter

[logger_root]
level=ERROR
handlers=consoleHandler

[logger_cwlogs]
level=ERROR
handlers=consoleHandler
qualname=cwlogs.push
propagate=0

[logger_reader]
level=ERROR
handlers=consoleHandler
qualname=cwlogs.push.reader
propagate=0

[logger_publisher]
level=ERROR
handlers=consoleHandler
qualname=cwlogs.push.publisher
propagate=0

[handler_consoleHandler]
class=logging.StreamHandler
level=ERROR
formatter=simpleFormatter
args=(sys.stderr,)

[formatter_simpleFormatter]
format=%(asctime)s - %(name)s - %(levelname)s - %(process)d - %(threadName)s - %(message)s
EOF

cat <<'EOF' >> ~/cloudwatchlog.conf
[general]
state_file=/var/lib/awslogs/agent-state
use_gzip_http_content_encoding = true
logging_config_file = /root/awslogs_logging.conf

[/var/log/bastion]
datetime_format = %b %d %H:%M:%S
buffer_duration = 5000
log_stream_name = HISTORY_LOG({instance_id})
initial_position = end_of_file
EOF
  if [ "${release}" == "Ubuntu" ]; then
cat <<'EOF' >> ~/cloudwatchSSHLog.conf

[/var/log/auth.log]
file = /var/log/auth.log
log_stream_name = SSH_LOG({instance_id})
datetime_format = %b %d %H:%M:%S
initial_position = end_of_file
EOF
  else
cat <<'EOF' >> ~/cloudwatchSSHLog.conf

[/var/log/secure]
file = /var/log/secure
log_stream_name = SSH_LOG({instance_id})
datetime_format = %b %d %H:%M:%S
initial_position = end_of_file
EOF

  fi


  cat /tmp/filename.txt >> ~/cloudwatchlog.conf
	cat /tmp/groupname.txt >> ~/cloudwatchlog.conf
	cat ~/cloudwatchSSHLog.conf >> ~/cloudwatchlog.conf
  cat /tmp/groupname.txt >> ~/cloudwatchlog.conf
}

function amazon_os () {
    echo "${FUNCNAME[0]} Started"
    chown root:ec2-user /usr/bin/script
    service sshd restart


	chown root:ec2-user  ${BASTION_MNT}
	chown root:ec2-user  ${BASTION_LOGFILE}
	chown root:ec2-user  ${BASTION_LOGFILE_SHADOW}
	chmod 662 ${BASTION_LOGFILE}
	chmod 662 ${BASTION_LOGFILE_SHADOW}
	chattr +a ${BASTION_LOGFILE}
	chattr +a ${BASTION_LOGFILE_SHADOW}
	touch /tmp/messages
	chown root:ec2-user /tmp/messages
	#Install CloudWatch Log service on AMZN
	yum update -y
	yum install -y awslogs


	writeDefaultConf

#    LINE=$(cat -n /etc/awslogs/awslogs.conf | grep '\[\/var\/log\/messages\]' | awk '{print $1}')
#    if [ ! $LINE ] || [ $LINE -lt 1 ]; then
#		LINE=$(cat -n /etc/awslogs/awslogs.conf | grep '\[\/var\/log\/bastion\]' | awk '{print $1}')
#	fi
#	if [ ! $LINE ] || [ $LINE -lt 1 ]; then
#		LINE=1
#	fi
#	END_LINE=$(echo $((${LINE}-1)))

#    head -${END_LINE} /etc/awslogs/awslogs.conf > /tmp/awslogs.conf
#    cat /tmp/awslogs.conf > /etc/awslogs/awslogs.conf
#	cat ~/cloudwatchlog.conf >> /etc/awslogs/awslogs.conf
  cat ~/cloudwatchlog.conf > /etc/awslogs/awslogs.conf

    export TMPREGION=$(grep region /etc/awslogs/awscli.conf)
    sed -i.back "s/${TMPREGION}/region = ${REGION}/g" /etc/awslogs/awscli.conf

    echo "${FUNCNAME[0]} Ended"
}

function cent_os () {

	chown root:centos ${BASTION_MNT}
	chown root:centos /usr/bin/script
	chown root:centos  /var/log/bastion/bastion.log
	chmod 662 /var/log/bastion/bastion.log
	touch /tmp/messages
	chown root:centos /tmp/messages

    restorecon -v /etc/ssh/sshd_config
    /bin/systemctl restart sshd.service

    # Install CloudWatch Log service on Centos Linux
    centos=`cat /etc/os-release | grep VERSION_ID | tr -d \VERSION_ID=\"`
    if [ "${centos}" == "7" ]; then

#        cat <<EOF >> ~/cloudwatchlog.conf
#[general]
#state_file = /var/awslogs/state/agent-state
#use_gzip_http_content_encoding = true
#logging_config_file = /var/awslogs/etc/awslogs.conf
#EOF
		writeDefaultConf


        curl https://s3.amazonaws.com/aws-cloudwatch/downloads/latest/awslogs-agent-setup.py -O
        chmod +x ./awslogs-agent-setup.py
        ./awslogs-agent-setup.py -n -r ${REGION} -c ~/cloudwatchlog.conf

		grepStr=$(grep "\[Unit\]" "/etc/systemd/system/awslogs.service" | head -n 1)
		grepLength=${#grepStr}

		if [ $grepLength -le 0 ] ; then
        cat << EOF >> /etc/systemd/system/awslogs.service
[Unit]
Description=The CloudWatch Logs agent
After=rc-local.service

[Service]
Type=simple
Restart=always
KillMode=process
TimeoutSec=infinity
PIDFile=/var/awslogs/state/awslogs.pid
ExecStart=/var/awslogs/bin/awslogs-agent-launcher.sh --start --background --pidfile $PIDFILE --user awslogs --chuid awslogs &

[Install]
WantedBy=multi-user.target
EOF
        fi
  else
        chown root:centos /var/log/bastion
        yum update -y
        yum install -y awslogs
        export TMPREGION=`cat /etc/awslogs/awscli.conf | grep region`
        sed -i.back "s/${TMPREGION}/region = ${REGION}/g" /etc/awslogs/awscli.conf

        writeDefaultConf
        export TMPGROUP=`cat /etc/awslogs/awslogs.conf | grep ^log_group_name`
        export TMPGROUP=`echo ${TMPGROUP} | sed 's/\//\\\\\//g'`
        sed -i.back "s/${TMPGROUP}/log_group_name = ${CWG}/g" /etc/awslogs/awslogs.conf




		cat ~/cloudwatchlog.conf >> /etc/awslogs/awslogs.conf
		yum install ec2-metadata -y
        export TMPREGION=`cat /etc/awslogs/awscli.conf | grep region`
        sed -i.back "s/${TMPREGION}/region = ${REGION}/g" /etc/awslogs/awscli.conf

    fi

    echo "${FUNCNAME[0]} Ended"
}


function ubuntu_os () {
    chown syslog:adm /var/log/bastion
    chown root:ubuntu /usr/bin/script

  	grepStr=$(grep "Added by Shell Script" "/etc/bash.bashrc")
    grepLength=${#grepStr}
    if [ $grepLength -le 0 ] ; then
cat <<'EOF' >> /etc/bash.bashrc
#Added by Shell Script
declare -rx IP=$(who am i --ips|awk '{print $5}')
EOF
    echo " declare -rx BASTION_LOG=${BASTION_MNT}/${BASTIONLOG}" >> /etc/bash.bashrc

cat <<'EOF' >> /etc/bash.bashrc
declare -rx PROMPT_COMMAND='history -a >(logger -t "ON: $(date)   [FROM]:${IP}   [USER]:${USER}   [PWD]:${PWD}" -s 2>>${BASTION_LOG})'
EOF
    fi
    chown root:ubuntu ${BASTION_MNT}
    chown root:ubuntu  ${BASTION_LOGFILE}
    chown root:ubuntu  ${BASTION_LOGFILE_SHADOW}
    chmod 662 ${BASTION_LOGFILE}
    chmod 662 ${BASTION_LOGFILE_SHADOW}
    chattr +a ${BASTION_LOGFILE}
    chattr +a ${BASTION_LOGFILE_SHADOW}
    touch /tmp/messages
    chown root:ubuntu /tmp/messages
    #Install CloudWatch logs on Ubuntu

#cat <<'EOF' >> ~/cloudwatchlog.conf
#[general]
#state_file = /var/awslogs/state/agent-state

#EOF

    writeDefaultConf

    curl https://s3.amazonaws.com/aws-cloudwatch/downloads/latest/awslogs-agent-setup.py -O
    export DEBIAN_FRONTEND=noninteractive
    apt-get install -y python
    chmod +x ./awslogs-agent-setup.py
    ./awslogs-agent-setup.py -n -r ${REGION} -c ~/cloudwatchlog.conf

    #Install Unit file for Ubuntu 16.04
    ubuntu=`cat /etc/os-release | grep VERSION_ID | tr -d \VERSION_ID=\"`
    if [ "${ubuntu}" == "16.04" ]; then
      grepStr2=$(grep "\[Unit\]" "/etc/systemd/system/awslogs.service" | head -n 1)
  		grepLength2=${#grepStr2}

  		if [ $grepLength2 -le 0 ] ; then
cat <<'EOF' >> /etc/systemd/system/awslogs.service
[Unit]
Description=The CloudWatch Logs agent
After=rc-local.service

[Service]
Type=simple
Restart=always
KillMode=process
TimeoutSec=infinity
PIDFile=/var/awslogs/state/awslogs.pid
ExecStart=/var/awslogs/bin/awslogs-agent-launcher.sh --start --background --pidfile $PIDFILE --user awslogs --chuid awslogs &

[Install]
WantedBy=multi-user.target
EOF
      fi
    fi
    echo "${FUNCNAME[0]} Ended"
}


function appLogConfig(){
	if [ -f "/root/appDeploy.py" ] ; then
		python appDeploy.py ${CLOUDWATCHGROUP}
	fi
}

function prevent_process_snooping() {
    # Prevent bastion host users from viewing processes owned by other users.
    mount -o remount,rw,hidepid=2 /proc
    awk '!/proc/' /etc/fstab > temp && mv temp /etc/fstab
    echo "proc /proc proc defaults,hidepid=2 0 0" >> /etc/fstab
    echo "${FUNCNAME[0]} Ended"
}

##################################### End Function Definitions
release=$(osrelease)

# Verify dependencies are installed.
verify_dependencies
# Assuming it is, setup environment variables.
setup_environment_variables

## set an initial value

# Read the options from cli input
TEMP=`getopt -o h:  --long help,enable: -n $0 -- "$@"`
eval set -- "${TEMP}"



#if [[ ${X11_FORWARDING} == "false" ]];then
#awk '!/X11Forwarding/' /etc/ssh/sshd_config > temp && mv temp /etc/ssh/sshd_config
#echo "X11Forwarding no" >> /etc/ssh/sshd_config
#fi


# Ubuntu Linux

if [ "${release}" == "Ubuntu" ]; then
	#Call function for Ubuntu
	ubuntu_os
# AMZN Linux
elif [ "${release}" == "AMZN" ]; then
	#Call function for AMZN
	amazon_os
# CentOS Linux
elif [ "${release}" == "AMZN2" ]; then
  amazon_os
elif [ "${release}" == "CentOS" ]; then
	#Call function for CentOS
	cent_os
else
	echo "[ERROR] Unsupported Linux Bastion OS"
	exit 1
fi
#call application log setting
appLogConfig


# Ubuntu Linux
if [ "${release}" == "Ubuntu" ]; then
	#Restart awslogs service
  service awslogs restart
  export DEBIAN_FRONTEND=noninteractive
  #apt-get install sysv-rc-conf -y
  #sysv-rc-conf awslogs on

  #Restart SSH
  service ssh stop
  service ssh start

  #Run security updates
  #apt-get install unattended-upgrades
	#echo "0 0 * * * unattended-upgrades -d" >> ~/mycron
	#crontab ~/mycron
	#rm ~/mycron
else
	# AMZN Linux
	if [ "${release}" == "AMZN" ]; then
		#Restart awslogs service
		sleep 3
		service awslogs restart
		#chkconfig awslogs on

  elif [ "${release}" == "AMZN2" ]; then
    sleep 3
    systemctl restart awslogsd
    #systemctl enable awslogsd.service
	elif [ "${release}" == "CentOS" ]; then
		centos=`cat /etc/os-release | grep VERSION_ID | tr -d \VERSION_ID=\"`
		if [ "${centos}" == "7" ]; then
			#Restart awslogs service
			sleep 3
			service awslogs restart
			#chkconfig awslogs on
		else
			sleep 3
			service awslogs stop
			sleep 3
			service awslogs start
			#chkconfig awslogs on
		fi
	fi
	#Run security updates
	#echo "0 0 * * * yum -y update --security" > ~/mycron
	#crontab ~/mycron
	#rm ~/mycron
fi


prevent_process_snooping

echo "Bootstrap complete."
