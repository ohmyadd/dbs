# Architecture
* infra: ovn sdn controller + docker network ovn driver(special)
* files: files to mount into app container
* topology: source.xml(export from draw.io) --front--> ir --back(docker-compose)--> (docker + ovn) instance

# Initial
* docker
```
curl -L get.docker.com | bash -s -- --mirror Aliyun
systemctl start docker
systemctl enable docker
```

* pip
```
yum install python3 python3-pip
pip3 install --upgrade pip
pip3 install docker-compose -i https://pypi.douban.com/simple
pip3 install -r topology/front/drawio_requirements.txt -i https://pypi.douban.com/simple
``` 

# Run
* run ovn
```
cd dbs/infra
docker-compose build
docker-compose pull
docker-compose up -d
docker logs infra_driver_1 #make sure driver is running 
```

* run exp instance
```
cd topology
cp xxx/somename.xml src/ # 
cd front
python3 drawio.py somename.xml # make sure this step generate ../ir/somename.app.yaml right
cd ../back
./app.sh somename up (down)
```

# Attention
* ovn network driver special behavior:
  * gateway argument is default set to the last ip of the subnet (deceive docker)
  * driver_opts com.ohmyadd.network.ovn.gateway is the real gateway ip (set in ovn)
  * For The Purpose OF: Container be able to occupy the real gateway ip
* drawio source
  * open [draw.io](https://draw.io)
  * import ovn2_2 chart xml in topology/src
  * modify it to what you want
    1. (ova -> open) arrow is the belong relation between container and netowrk
    2. (diamon -> diamond) arror is a simplify network within two containers
    3. process type is container
    4. rectangle type is network
  * finally you can export the chart as xml
  * **do not** export as compressed file
  * **do not** use formatted text in any component in chart
