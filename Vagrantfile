# -*- mode: ruby -*-
# vi: set ft=ruby :
VAGRANTFILE_API_VERSION = "2"


$script = <<SCRIPT
### set up vagrant user ###
echo '. "/vagrant/services/vagrant/profile.sh"' >> /home/vagrant/.profile

### hosts ###
printf "\n\n127.0.0.1 perma.dev\n127.0.0.1 users.perma.dev" >> /etc/hosts

### basic packages ###
apt-get -y update
apt-get install -y git build-essential

### install mysql ###
# set root password to 'root'
debconf-set-selections <<< 'mysql-server mysql-server/root_password password root'
debconf-set-selections <<< 'mysql-server mysql-server/root_password_again password root'
# install package
apt-get -y install mysql-server libmysqlclient-dev
# hook up settings file
rm /etc/mysql/my.cnf
ln -s /vagrant/services/mysql/my.cnf /etc/mysql/
# disable apparmor and run mysql as 'vagrant' user so we can store data in /vagrant
ln -s /etc/apparmor.d/usr.sbin.mysqld /etc/apparmor.d/disable/
apparmor_parser -R /etc/apparmor.d/usr.sbin.mysqld
chmod a+rw /var/lib/mysql /var/run/mysqld/ /usr/share/mysql /var/log/mysql
# fix bug that recreates folder with wrong user on startup
sed -i 's/-o mysql/-o vagrant/' /etc/init/mysql.conf
restart mysql

### create perma database ###
mysql -uroot -proot -e "create database perma character set utf8; grant all on perma.* to perma@'localhost' identified by 'perma';"

### install Python packages ###
apt-get install -y python-dev # for stuff that compiles from source
apt-get install -y libffi-dev # dependency for cryptography
sudo apt-get install -y libxml2-dev libxslt1-dev # dependencies for lxml
apt-get install -y python-pip
pip install --upgrade pip virtualenvwrapper
export WORKON_HOME=/home/vagrant/.virtualenvs
source /usr/local/bin/virtualenvwrapper.sh
mkvirtualenv perma
workon perma
pip install --upgrade distribute # dependency for mysql
pip install -r /vagrant/perma_web/requirements.txt

### install task queue (rabbitmq and celery) ###
apt-get install -y rabbitmq-server
cp /vagrant/services/celery/celery.conf /etc/init/celery.conf
start celery

### install nginx and uwsgi ###
# (we're not using these at the moment)
apt-get install -y nginx-full uwsgi
ln -s /vagrant/services/nginx/nginx.conf /etc/nginx/sites-enabled/
ln -s /vagrant/services/uwsgi/perma.ini /etc/uwsgi/apps-enabled/
cp /vagrant/services/uwsgi/uwsgi.conf /etc/init/uwsgi.conf
#service nginx start
#service uwsgi start

### install phantomjs ###
# have to download manually since the apt-get is currently back at version 1.4
apt-get install -y fontconfig
cd /usr/local/share
wget https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-1.9.7-linux-x86_64.tar.bz2
tar xjf phantomjs-1.9.7-linux-x86_64.tar.bz2
ln -s /usr/local/share/phantomjs-1.9.7-linux-x86_64/bin/phantomjs /usr/bin/
rm phantomjs-1.9.7-linux-x86_64.tar.bz2

### clean up permissions ###
chown -R vagrant /home/vagrant/.virtualenvs
SCRIPT


Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.network :forwarded_port, guest: 8000, host: 8000
  puts("loading ...")

  if ENV['REGENERATE']
    # generate our custom build
    # call as `REGENERATE=1 vagrant up`
    puts("regenerating ...")
    # base our config on Ubuntu Precise Pangolin (current Long Term Support release)
    config.vm.box = "precise64"
    config.vm.box_url = "http://files.vagrantup.com/precise64.box"
    config.vm.provision "shell", inline: $script

  else
    puts("using prebuilt perma virtual machine ...")
    config.vm.box = "perma_0.1"
    #config.vm.box_url = "http://files.vagrantup.com/precise64.box"
  end
end
