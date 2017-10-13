FROM python:2-stretch
ENV PYTHONUNBUFFERED 1
RUN mkdir -p /perma/perma_web
WORKDIR /perma/perma_web

# npm
RUN curl -sL https://deb.nodesource.com/setup_6.x | bash -
RUN apt-get install nodejs
ADD package.json /perma/perma_web
RUN npm install

# pip
ADD requirements.txt /perma/perma_web
RUN pip install -U pip; pip install -r requirements.txt --src /usr/local/src

# phantomjs
RUN wget https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2
RUN tar xvjf phantomjs-2.1.1-linux-x86_64.tar.bz2
RUN mv phantomjs-2.1.1-linux-x86_64 /usr/local/share
RUN ln -sf /usr/local/share/phantomjs-2.1.1-linux-x86_64/bin/phantomjs /usr/local/bin
RUN rm phantomjs-2.1.1-linux-x86_64.tar.bz2