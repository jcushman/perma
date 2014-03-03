# stuff run when the vagrant user logs in

# for virtualenvwrapper
# put virtualenvs in /vagrant so they can be inspected by PyCharm running on host computer
export WORKON_HOME=/home/vagrant/.virtualenvs
source /usr/local/bin/virtualenvwrapper.sh

# start celery
# TODO: celery is automatically started on boot, so this shouldn't be necessary, but for some reason it fails at that point
sudo start celery

# mysql also seems to fail sometimes
sudo start mysql

# prepare for Django work
workon perma
cd /vagrant/perma_web