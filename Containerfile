# Use the same base image version as the clams-python python library version
FROM ghcr.io/clamsproject/clams-python-jdk8:1.0.9
# See https://github.com/orgs/clamsproject/packages?tab=packages&q=clams-python for more base images
# IF you want to automatically publish this image to the clamsproject organization, 
# 1. you should have generated this template without --no-github-actions flag
# 1. to add arm64 support, change relevant line in .github/workflows/container.yml 
#     * NOTE that a lots of software doesn't install/compile or run on arm64 architecture out of the box 
#     * make sure you locally test the compatibility of all software dependencies before using arm64 support 
# 1. use a git tag to trigger the github action. You need to use git tag to properly set app version anyway

################################################################################
# DO NOT EDIT THIS SECTION
ARG CLAMS_APP_VERSION
ENV CLAMS_APP_VERSION ${CLAMS_APP_VERSION}
################################################################################

################################################################################
# clams-python base images are based on debian distro
# install more system packages as needed using the apt manager
################################################################################
RUN apt update
RUN apt install -y maven curl
ADD https://github.com/dbpedia-spotlight/dbpedia-spotlight-model/archive/daf53090b3ea9d1ddd939c455e4c65a18d5b4d2f.tar.gz /dbps.tar.gz
RUN tar -x -z -f /dbps.tar.gz -C / && mv /dbpedia-spotlight-model-daf53090b3ea9d1ddd939c455e4c65a18d5b4d2f /dbps
WORKDIR /dbps
RUN mvn package
RUN curl -o /dbps/en.tar.gz "https://databus.dbpedia.org/dbpedia/spotlight/spotlight-model/2022.03.01/spotlight-model_lang=en.tar.gz" -L
RUN tar -x -f en.tar.gz -z
RUN apt purge -y maven curl && apt autoremove -y
################################################################################
# main app installation
COPY ./ /app
WORKDIR /app
RUN pip3 install -r requirements.txt

# default command to run the CLAMS app in a production server 
CMD /bin/bash /app/wrapper_script.sh
################################################################################
