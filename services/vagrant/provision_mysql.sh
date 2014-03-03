#!/bin/sh

# initialize the mysql directory and create the perma database
# both commands will fail harmlessly if they've already been completed
mysql_install_db --user=mysql --datadir=/mysql_data/ &&
  mysqladmin -u root password root
start mysql
mysql -uroot -proot -e "create database perma character set utf8;" && mysql -uroot -proot -e "grant all on perma.* to perma@'localhost' identified by 'perma';"
