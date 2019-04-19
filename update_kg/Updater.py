"""
After upload original data:
1.1 get entity json head
1.2 get event json head
1.3 cluster entity
1.4 cluster event
2.1 insert prototype hasName for entity
2.2 insert prototype type
2.3 insert prototype justification
DUMP KG IF NEEDED
3.1 insert SuperEdge
DUMP KG IF NEEDED
"""
import sys
import os
import json
import random
import string
from datetime import datetime
from SPARQLWrapper import SPARQLWrapper
import requests
mln_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '../gaia-clustering/multi_layer_network/src')
sys.path.append(mln_path)
from namespaces import namespaces, ENTITY_TYPE_STR
mln_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), '../gaia-clustering/multi_layer_network/test')
sys.path.append(mln_path)
import baseline2_exe, from_jsonhead2cluster
sys.path.append(".")
from sparqls import *


class Updater(object):
    def __init__(self, endpoint, name, outdir, graph=None, has_jl=False):
        if '3030' in endpoint:
            self.select = SPARQLWrapper(endpoint.rstrip('/') + '/query')
            self.update = SPARQLWrapper(endpoint.rstrip('/') + '/update')
            self.graphdb = False
        else:
            self.select = SPARQLWrapper(endpoint)
            self.update = SPARQLWrapper(endpoint)
            self.graphdb = True
        self.select.setReturnFormat('json')
        self.update.setMethod('POST')
        self.endpoint = endpoint.rstrip('/')

        self.outdir = outdir
        self.name = name

        self.prefix = ''.join(['PREFIX %s: <%s>\n' % (abbr, full) for abbr, full in namespaces.items()])
        self.nt_prefix = ''.join(['@prefix %s: <%s> .\n' % (abbr, full) for abbr, full in namespaces.items()])
        self.system = 'http://www.isi.edu/TA2'

        self.entity_json = {}
        self.event_json = {}

        self.entity_jl = []
        self.event_jl = []
        self.relation_jl = []

        self.graph = graph
        self.has_jl = has_jl

    def run_delete_ori(self):
        delete_ori = delete_ori_cluster()
        print("start delete original clusters", datetime.now().isoformat())
        self.update_sparql(delete_ori)
        delete_ori_mem = delete_ori_clusterMember()
        print("start delete original clusters Memberships", datetime.now().isoformat())
        self.update_sparql(delete_ori_mem)
        print("Done. ", datetime.now().isoformat())

    def run_load_jl(self):
        if self.has_jl:
            print("start loading entity jl", datetime.now().isoformat())
            self.entity_jl = self.load_jl(self.outdir + '/entity-clusters.jl')
            print("start loading event jl", datetime.now().isoformat())
            self.event_jl = self.load_jl(self.outdir + '/event-clusters.jl')
        else:
            self.generate_jl()
        print("Done. ", datetime.now().isoformat())

    def run_system(self):
        print("start inserting system", datetime.now().isoformat())
        insert_system = system()
        self.upload_data([insert_system])
        print("Done. ", datetime.now().isoformat())

    def run_entity_nt(self):
        print("start inserting triples for entity clusters", datetime.now().isoformat())
        entity_nt = self.convert_jl_to_nt(self.entity_jl, 'aida:Entity', 'entities')
        self.upload_data(entity_nt)
        print("Done. ", datetime.now().isoformat())

    def run_event_nt(self):
        print("start inserting triples for event clusters", datetime.now().isoformat())
        event_nt = self.convert_jl_to_nt(self.event_jl, 'aida:Event', 'events')
        self.upload_data(event_nt)
        # if self.graphdb:
        #     input('upload nt and continue')
        print("Done. ", datetime.now().isoformat())

    def run_relation_nt(self):
        print("start getting relation jl", datetime.now().isoformat())
        relation_jl = self.generate_relation_jl()

        print("start inserting triples for relation clusters", datetime.now().isoformat())
        relation_nt = self.convert_jl_to_nt(relation_jl, 'aida:Relation', 'relations')
        self.upload_data(relation_nt)
        # if self.graphdb:
        #     input('upload nt and continue')
        print("Done. ", datetime.now().isoformat())

    def run_insert_proto(self):
        print("start inserting prototype name", datetime.now().isoformat())
        insert_name = proto_name(self.graph)
        self.update_sparql(insert_name)

        print("start inserting prototype type(category)", datetime.now().isoformat())
        insert_type = proto_type(self.graph)
        self.update_sparql(insert_type)

        print("start inserting prototype justification", datetime.now().isoformat())
        insert_justi = proto_justi(self.graph)
        self.update_sparql(insert_justi)

        print("start inserting prototype type-assertion justification", datetime.now().isoformat())
        insert_type_justi = proto_type_assertion_justi(self.graph)
        self.update_sparql(insert_type_justi)
        print("Done. ", datetime.now().isoformat())

    def run_super_edge(self):
        print("start inserting superEdge", datetime.now().isoformat())
        insert_se = super_edge(self.graph)
        self.update_sparql(insert_se)

        print("start inserting superEdge justifications", datetime.now().isoformat())
        insert_se_justi = super_edge_justif(self.graph)
        self.update_sparql(insert_se_justi)
        print("Done. ", datetime.now().isoformat())

    def get_json_head_entity(self):
        ent_q = get_entity()
        for x in self.select_bindings(ent_q)[1]:
            if 'linkTarget' in x:
                link_target = x['linkTarget']['value']
            else:
                link_target = self.random_str()
            name = x['name']['value'] if 'name' in x else ''
            txt_grained_type = []
            try:
                name = json.loads(x['translate']['value'])[0]
            except Exception:
                # TODO: get name from prefLabel ? if there is no hasName or textValue
                pass
            try:
                txt_grained_type = json.loads(x['txt_grained_type']['value'])
            except Exception:
                pass
            # TODO in cluster: make use of fine-grained types
            self.entity_json[x['e']['value']] = [name, x['type']['value'], link_target, txt_grained_type]

    def get_json_head_event(self):
        evt_q = get_event()
        for x in self.select_bindings(evt_q)[1]:
            evt_uri = x['e']['value']
            if evt_uri not in self.event_json:
                self.event_json[evt_uri] = {'type': x['type']['value'], 'doc': x['doc']['value'], 'text': []}
                for t in ENTITY_TYPE_STR:
                    self.event_json[evt_uri][t] = []

            cur = None
            try:
                cur = json.loads(x['translate']['value'])[0]
            except Exception:
                if 'text' in x:
                    cur = x['text']['value']
            if cur:
                self.event_json[evt_uri]['text'].append(cur)

            if 'ent' in x:
                ent = x['ent']['value']
                ent_name = self.entity_json[ent][0]
                ent_type = self.entity_json[ent][1]
                self.event_json[evt_uri][ent_type].append([ent, ent_name])

    def generate_jl(self):
        print("start getting json head", datetime.now().isoformat())
        self.get_json_head_entity()
        self.get_json_head_event()
        print(len(self.entity_json), len(self.event_json))

        # run Xin's clustering scripts

        print("start getting entity jl", datetime.now().isoformat())
        self.entity_jl, entity_edgelist_G = from_jsonhead2cluster.run(self.entity_json, self.name)
        print("start getting event jl", datetime.now().isoformat())
        self.entity_jl = baseline2_exe.run(entity_edgelist_G, self.entity_json, self.event_json, self.name)

    def convert_jl_to_nt(self, jl, aida_type, key_type):
        res = []
        for line in jl:
            members = line
            cluster_uri = '%s-cluster' % members[0]
            prototype_uri = '%s-prototype' % members[0]
            res.append(self.wrap_cluster(cluster_uri, prototype_uri, aida_type))
            memberships = '\n'.join([self.wrap_membership(cluster_uri, m) for m in members])
            res.append(memberships)
        return res

    def generate_relation_jl(self):
        groups = {}
        rel_json = {}
        q = get_relation(self.graph)
        for x in self.select_bindings(q)[1]:
            rel_uri = x['e']['value']
            if rel_uri not in rel_json:
                rel_json[rel_uri] = {'links': [], 'type': x['type']['value'].rsplit('#', 1)[-1]}

                pred = x['p']['value']
                cluster = x['cluster']['value']
                rel_json[rel_uri]['links'].append((pred.rsplit('#', 1)[-1], cluster.rsplit('#', 1)[-1]))
        for rel, attrs in rel_json.items():
            attr = attrs['type'] + str(sorted(attrs['links']))
            if attr not in groups:
                groups[attr] = []
            groups[attr].append(rel)

        jl = [v for v in groups.values()]
        with open(self.outdir + '/relation-clusters.jl', 'w') as f:
            for line in jl:
                json.dump(line, f)
                f.write('\n')
        return jl

    def select_bindings(self, q):
        if self.graphdb:
            self.select.setQuery(self.prefix + q)
        else:
            self.select.setQuery(self.prefix + q)
        ans = self.select.query().convert()
        return ans['head']['vars'], ans['results']['bindings']

    def update_sparql(self, q):
        if self.graphdb:
            req_ = requests.post(self.endpoint + '/statements', params={'update': self.prefix + q})
            print(req_, req_.content)
        else:
            self.update.setQuery(self.prefix + q)
            print('  ', self.update.query().convert())

    def upload_data(self, triple_list):
        data = self.nt_prefix + '\n'.join(triple_list)
        if self.graphdb:
            # print('  start dump nt to file with triple list length %d' % len(triple_list))
            # with open(self.name + self.random_str(8) + '.ttl', 'w') as f:
            #     f.write(data)
            ep = self.endpoint + '/statements'
            if self.graph:
                print('!!! not support graph now -- will insert into default graph !!!')
        else:
            ep = self.endpoint + '/data'
            if self.graph:
                ep += ('?graph=' + self.graph)
        print('  start a post request on %s, with triple list length %d' % (ep, len(triple_list)))
        r = requests.post(ep, data=data, headers={'Content-Type': 'text/turtle'})
        print('  response ', r.content)
        return r.content

    def wrap_membership(self, cluster, member):
        membership = '''
        [] a aida:ClusterMembership ;
           aida:cluster <%s> ;
           aida:clusterMember <%s> ;
           aida:confidence [
                a aida:Confidence ;
                aida:confidenceValue  "1.0"^^xsd:double ;
                aida:system <%s> ] ;
           aida:system <%s> .
        ''' % (cluster, member, self.system, self.system)
        return membership.strip('\n')

    def wrap_cluster(self, cluster, prototype, prototype_type):
        cluster = '''
        <%s> a               aida:SameAsCluster ;
             aida:prototype  <%s> ;
             aida:system     <%s> .
        <%s> a %s .
        ''' % (cluster, prototype, self.system, prototype, prototype_type)
        return cluster.strip('\n')

    @staticmethod
    def load_jl(file_path):
        jl = []
        with open(file_path) as f:
            for line in f.readlines():
                jl.append(json.loads(line))
        return jl

    @staticmethod
    def random_str(length=32):
        return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(length)])
