import argparse
from bs4 import BeautifulSoup
import json
from lapps.discriminators import Uri
import re
import requests
from SPARQLWrapper import SPARQLWrapper, JSON
from typing import Union, Any, List

from clams import ClamsApp, Restifier
from mmif import Mmif, View, Annotation, Document, AnnotationTypes, DocumentTypes

sparql = SPARQLWrapper("http://dbpedia.org/sparql")


class DbpediaWrapper(ClamsApp):

    def __init__(self):
        super().__init__()
        self.address = "http://localhost:2222/rest/annotate"
        self.reqheaders = {'Accept': 'application/json'}

    def _appmetadata(self):
        # see https://sdk.clams.ai/autodoc/clams.app.html#clams.app.ClamsApp._load_appmetadata
        # Also check out ``metadata.py`` in this directory. 
        # When using the ``metadata.py`` leave this do-nothing "pass" method here. 
        pass

    def _annotate(self, mmif: Union[str, dict, Mmif], **parameters) -> Mmif:
        # see https://sdk.clams.ai/autodoc/clams.app.html#clams.app.ClamsApp._annotate

        def _get_qid(uri: str) -> List[str]:
            """
            Query dbpedia endpoint to retrieve Wikidata QIDs
            :param uri: the dbpedia URI.
            :return: a list of QIDs
            """
            ent = uri.rpartition("/")[-1]
            sparql.setQuery(f"""
                PREFIX : <http://dbpedia.org/resource/>
                SELECT DISTINCT ?wikidata_concept
                WHERE {{dbr:{ent} owl:sameAs ?wikidata_concept
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

        def _post_request(text: str) -> Any:
            """
            Makes the Spotlight request and posts it to the server.
            :param text: the input text to run through Spotlight.
            :return: json body of the response.
            """
            payload = {'text': text}
            res = requests.post(url=self.address, data=payload, headers=self.reqheaders)
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
            if 'Resources' not in json_body:
                raise Exception("No resources found in Spotlight response.")
            for resource in json_body['Resources']:
                named_ents[resource['@surfaceForm']] = dict(text=resource['@surfaceForm'],
                                                            offset_start=resource['@offset'],
                                                            offset_end=int(resource['@offset']) + len(
                                                                resource['@surfaceForm']),
                                                            category='')
                if resource['@URI']:
                    uri = resource['@URI']
                    page = requests.get(uri)
                    soup = BeautifulSoup(page.content, "html.parser")
                    ent_span = soup.find("span", class_="text-nowrap")
                    pattern = re.compile(r'\w+(?=</a>)')
                    category = pattern.search(str(ent_span))
                    named_ents[resource['@surfaceForm']]['category'] = category.group(0)
                    grounding = [uri]
                    grounding.extend(list(_get_qid(uri)))
                    named_ents[resource['@surfaceForm']]['grounding'] = grounding
                else:
                    named_ents[resource['@surfaceForm']]['grounding'] = []

            return named_ents

        if not isinstance(mmif, Mmif):
            mmif: Mmif = Mmif(mmif)
        for doc in mmif.get_documents_by_type(DocumentTypes.TextDocument):
            res_json = _post_request(doc.text_value)
            entities = _get_ne_links(res_json)
            did = f"{doc.parent}:{doc.id}" if doc.parent else doc.id
            new_view = mmif.new_view()
            self.sign_view(new_view)
            new_view.new_contain(Uri.NE, document=did)
            for e in entities:
                anno = new_view.new_annotation(Uri.NE)
                anno.add_property('start', entities[e]['offset_start'])
                anno.add_property('end', entities[e]['offset_end'])
                anno.add_property('category', entities[e]['category'])
                anno.add_property('text', entities[e]['text'])
                anno.add_property('grounding', entities[e]['grounding'])
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
    parser.add_argument(
        "--port", action="store", default="5000", help="set port to listen"
    )
    parser.add_argument("--production", action="store_true", help="run gunicorn server")
    parser.add_argument("-t", "--test", action='store_true', help="bypass the server")
    parser.add_argument("infile", nargs='?', help="input MMIF file")
    parser.add_argument("outfile", nargs='?', help="output file")

    parsed_args = parser.parse_args()

    if parsed_args.test:
        test(parsed_args.infile, parsed_args.outfile)
    else:
        # create the app instance
        app = DbpediaWrapper()

        http_app = Restifier(app, port=int(parsed_args.port)
                             )
        if parsed_args.production:
            http_app.serve_production()
        else:
            http_app.run()
