#!/bin/bash

echo ! > /etc/frr/frr.conf
echo "log file /var/log/frr/debug.log debugging" >> /etc/frr/frr.conf
echo ! >> /etc/frr/frr.conf

for i in `env`
do
    key=`echo $i | awk -F"=" '{print $1}'`
    eval val=\$$key
    if [[ $key == CFG_* ]];
    then
      name=${key:4}
      echo $name"-----""${val}"
      sed -i "s/${name}=no/${name}=yes/" /etc/frr/daemons
      echo ! >> /etc/frr/frr.conf
      echo "log file /var/log/frr/${name}.log debugging" >> /etc/frr/frr.conf
      echo "${val}" >> /etc/frr/frr.conf
      echo ! >> /etc/frr/frr.conf
    fi
done
