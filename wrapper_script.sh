#!/bin/bash

# Java command for running the server
java -Dfile.encoding=UTF-8 -Xmx10G -jar 
/dbps/rest/target/rest-1.1-jar-with-dependencies.jar /dbps/en 
http://0.0.0.0:2222/rest &

# Run the clams app
python3 /app/app.py --production

# Bring the primary process back into the foreground
# and leave it there
fg %1 