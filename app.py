import argparse

from lapps.discriminators import Uri
import logging
import requests
from requests.adapters import HTTPAdapter
from SPARQLWrapper import SPARQLWrapper, JSON
from typing import Union, Any, List
from urllib3.util import Retry

from clams import ClamsApp, Restifier
from mmif import Mmif, View, Annotation, Document, AnnotationTypes, DocumentTypes

sparql = SPARQLWrapper("http://dbpedia.org/sparql")


class DbpediaWrapper(ClamsApp):

    def __init__(self, address="localhost:2222"):
        super().__init__()
        self.address = "http://{}/rest/annotate".format(address)
        self.reqheaders = {'Accept': 'application/json'}
        self.session = requests.Session()
        self.session.headers.update(self.reqheaders)
        retry_adapter = HTTPAdapter(max_retries=Retry(total=10, backoff_factor=0.1, allowed_methods={'GET', 'POST'},
                                                      status_forcelist=[502, 503, 504]))
        self.session.mount('http://', retry_adapter)

    def _appmetadata(self):
        # see https://sdk.clams.ai/autodoc/clams.app.html#clams.app.ClamsApp._load_appmetadata
        # Also check out ``metadata.py`` in this directory. 
        # When using the ``metadata.py`` leave this do-nothing "pass" method here. 
        pass

    def _annotate(self, mmif: Union[str, dict, Mmif], **parameters) -> Mmif:
        # see https://sdk.clams.ai/autodoc/clams.app.html#clams.app.ClamsApp._annotate
        self.logger.debug(f"Parameters: {parameters}")

        def _get_qid(uri: str) -> List[str]:
            """
            Query dbpedia endpoint to retrieve Wikidata QIDs
            :param uri: the dbpedia URI.
            :return: a list of QIDs
            """
            sparql.setQuery(f"""
                SELECT DISTINCT ?wikidata_concept
                WHERE {{<{uri}> owl:sameAs ?wikidata_concept
                  FILTER (regex(str(?wikidata_concept), \"www.wikidata.org\"))
                }}
                LIMIT 10
            """)
            sparql.setReturnFormat(JSON)
            res = sparql.query().convert()
            qids = []
            for binding in res['results']['bindings']:
                for concept in binding.values():
                    qids.append(concept['value'])
            return qids

        def _post_request(text: str, **kwargs) -> Any:
            """
            Makes the Spotlight request and posts it to the server.
            :param text: the input text to run through Spotlight.
            :param kwargs: additional parameters for filtering entities.
            :return: json body of the response.
            """
            payload = {'text': text}
            payload.update(**kwargs)
            res = self.session.post(url=self.address, data=payload)
            # raise http error, if there is one
            res.raise_for_status()
            out_json = res.json()
            if out_json is None:
                raise Exception("Invalid json output: {}".format(res.text))
            return out_json

        def _get_ne_links(json_body) -> dict:
            """
            Parse the response json for relevant properties and returns them in a dictionary.
            """
            named_ents = {}
            type_mappings = {'person': {'dbpedia:person', 'schema:person', 'dbpedia:fictionalcharacter'},
                             'location': {'dbpedia:place', 'dbpedia:location', 'schema:place'},
                             'organization': {'dbpedia:organisation', 'schema:organization'},
                             'product': {'schema:product'}, 'event': {'dbpedia:event', 'schema:event'},
                             'title': {'dbpedia:work', 'schema:creativework'}}

            if 'Resources' not in json_body:
                raise Exception("No resources found in Spotlight response.")
            for resource in json_body['Resources']:
                self.logger.debug(f"Found resource {resource['@surfaceForm']}, {resource['@URI']}")
                named_ents[resource['@surfaceForm']] = dict(text=resource['@surfaceForm'],
                                                            offset_start=int(resource['@offset']),
                                                            offset_end=int(resource['@offset']) + len(
                                                                resource['@surfaceForm']),
                                                            category='')
                # assign the entity type
                if resource['@types']:
                    entity_types: list = resource['@types'].casefold().split(',')
                    for m in type_mappings:
                        if type_mappings[m].intersection(entity_types):
                            named_ents[resource['@surfaceForm']]['category'] = m
                            break
                # grounding
                if resource['@URI']:
                    uri = resource['@URI']
                    grounding = [uri]
                    grounding.extend(list(_get_qid(uri)))
                    named_ents[resource['@surfaceForm']]['grounding'] = grounding
                else:
                    named_ents[resource['@surfaceForm']]['grounding'] = []

            return named_ents

        # ensure that server is ready
        self.logger.debug("Waiting for server to be ready...")
        self.session.get(self.address)
        if not isinstance(mmif, Mmif):
            mmif: Mmif = Mmif(mmif)
        for doc in mmif.get_documents_by_type(DocumentTypes.TextDocument):
            self.logger.debug(f"Processing document {doc.id} @ {doc.location_path()}")
            res_json = _post_request(doc.text_value, **parameters)
            self.logger.debug(f"Response: {res_json.keys()}")
            entities = _get_ne_links(res_json)
            self.logger.debug(f"Found {len(entities)} entities.")
            did = f"{doc.parent}:{doc.id}" if doc.parent else doc.id
            new_view = mmif.new_view()
            self.logger.debug(f"Created new view {new_view.id} and siging with {parameters}")
            self.sign_view(new_view, parameters)
            new_view.new_contain(Uri.NE, document=did)
            for e in entities:
                anno = new_view.new_annotation(Uri.NE)
                anno.add_property('start', entities[e]['offset_start'])
                anno.add_property('end', entities[e]['offset_end'])
                anno.add_property('category', entities[e]['category'])
                anno.add_property('text', entities[e]['text'])
                anno.add_property('grounding', entities[e]['grounding'])
                self.logger.debug(f"Created annotation {anno.id} with grounding {entities[e]['grounding']}")
        return mmif


def test(infile, outfile) -> None:
    """
    Run dbpedia spotlight on an input MMIF file. Calls the `annotate()` method
    in the DBPediaWrapper class. Prints a summary of the views in the end result.
    :param infile: the MMIF file to add annotations to.
    :param outfile: the name of the output MMIF file.
    """
    app = DbpediaWrapper()
    print(app.appmetadata(pretty=True))
    with open(infile) as fh_in, open(outfile, 'w') as fh_out:
        mmif_out_as_string = app.annotate(fh_in.read(), pretty=True)
        mmif_out = Mmif(mmif_out_as_string)
        fh_out.write(mmif_out_as_string)
        for view in mmif_out.views:
            print("View id={} annotations={} app={}".format(view.id, len(view.annotations), view.metadata['app']))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", action="store", default="5000", help="set port to listen")
    parser.add_argument("--production", action="store_true", help="run gunicorn server")
    parser.add_argument("-a", "--address", default="localhost:2222", help="set listening address for spotlight server")
    parser.add_argument("-t", "--test", action='store_true', help="bypass the server")
    parser.add_argument("infile", nargs='?', help="input MMIF file")
    parser.add_argument("outfile", nargs='?', help="output file")

    parsed_args = parser.parse_args()

    if parsed_args.test:
        test(parsed_args.infile, parsed_args.outfile)
    else:
        # create the app instance
        app = DbpediaWrapper(address=parsed_args.address)

        http_app = Restifier(app, port=int(parsed_args.port))
        # for running the application in production mode
        if parsed_args.production:
            http_app.serve_production()
        # development mode
        else:
            app.logger.setLevel(logging.DEBUG)
            http_app.run()
