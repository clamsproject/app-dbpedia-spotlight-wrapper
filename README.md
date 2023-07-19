# DBpedia Spotlight Wrapper app

This repository provides a wrapper for using the DBpedia Spotlight service to perform named entity recognition
and linking.

## User instruction

General user instruction for CLAMS apps is available at [CLAMS Apps documentation](https://apps.clams.ai/clamsapp/).

Below is a list of additional information specific to this app.

### System requirments

- Python3 with the `clams-python` module installed, to run the app locally
- `docker` to run the app in a Docker container (as a HTTP server).
- An HTTP client utility (such as `curl`) to invoke and execute analysis.
- 10GB of RAM to run the DBpedia Spotlight service.

### Building and running the Docker image

From the project directory, run the following in your terminal to build the Docker image from the included Dockerfile:

```bash
docker build -t dbpedia-spotlight-wrapper -f Containerfile .
```

Then to create a Docker container using that image, run:

```bash
docker run -v /path/to/data/directory:/data -p <port>:5000 <app_name>
```

where /path/to/data/directory is the location of your media files or MMIF objects and `<port>` is the host port number you want your container to be listening to. The HTTP inside the container will be listening to `5000` by default.

_Note_: on newer Mac computers using ARM architecture, it may be necessary to use `5001` instead. 

Once the app is running as an HTTP server, to invoke the app and get automatic annotations, simply send a POST request to the app with a MMIF input as request body.

MMIF input files can be obtained from outputs of other CLAMS apps, or you can create an empty MMIF that only contains source media locations using the `clams source` command. See the help message for a more detailed instructions.

```bash
clams source --help
```
(Make sure you installed the same `clams-python` package version specified in the requirements.txt.)

### Configurable runtime parameter

(Parameters should be already well-described in the app metadata. But you can use this space to show examples, for instance.)
