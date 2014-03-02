# stuff run when the vagrant user logs in

# for virtualenvwrapper
# put virtualenvs in /vagrant so they can be inspected by PyCharm running on host computer
export WORKON_HOME=/home/vagrant/.virtualenvs
source /usr/local/bin/virtualenvwrapper.sh

workon perma

cd /vagrant/perma_web