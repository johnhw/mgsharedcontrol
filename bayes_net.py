import yaml
from libpgm.graphskeleton import GraphSkeleton
from libpgm.orderedskeleton import OrderedSkeleton
from libpgm.nodedata import NodeData
from libpgm.discretebayesiannetwork import DiscreteBayesianNetwork
from libpgm.tablecpdfactorization import TableCPDFactorization
from collections import defaultdict
import pydot
import pprint
import numpy as np
import logging

def normalise_name(n):
    if n.startswith('~'):
        return n[1:]
    return n
    
def is_negated(n):
    return n.startswith('~')
    
def parse_truth_table(truth_table, parents):
    cond_table = {}
    for row, prob in truth_table.iteritems():
        cond_name = []
        for i,p in enumerate(parents):
            on_true = row[i]=='t'
            
            if is_negated(p):
                on_true = not on_true
            if on_true:
                cond_name += ["'T'"] 
            else:
                cond_name += ["'F'"]
        cond_def = "[%s]" % ", ".join(cond_name)
        cond_table[cond_def] = [prob, 1.0-prob]
    return cond_table
    
def make_node(truth_table, parents, node_type):
    pgm_node = {}
    pgm_node["numoutcomes"] = 2
    pgm_node["vals"] = ["T", "F"]
    pgm_node["parents"] = parents
    pgm_node["cprob"] = truth_table
    pgm_node["type"] = node_type
    return pgm_node

    

class BayesNet(object):
    def __init__(self, nodes):
        
        self.nodes = {}
        
        self.children = defaultdict(list)
        self.parents = defaultdict(list)
        self.outputs = {}
        for name, node_spec in nodes.iteritems():
            node_type = node_spec["type"]
            if node_type=="inferred":
                parents = node_spec["parents"]
                # store the relationship between these elements
                for parent in parents:
                    normalised = normalise_name(parent)
                    self.parents[name].append(normalised)
                    self.children[normalised].append(name)
                truth_table = parse_truth_table(node_spec["p"], parents)
                node = make_node(truth_table, parents, node_type)
                self.nodes[name] = node
                
            if node_type=="fsm_input":
                node = make_node([1.0, 0.0], None, node_type)
                self.nodes[name] = node
                
            if node_type=="sensor_input":
                proxy_node = make_node([1.0, 0.0], None, "proxy")
                proxy_name = "_proxy_%s" % name
                self.nodes[proxy_name] = proxy_node
                self.children[proxy_name].append(name)
                node = make_node({"['T']":[1.0, 0.0], "['F']":[0.0, 1.0]}, [proxy_name], node_type)
                self.nodes[name] = node
            if node_type=="output":
                self.outputs[name] = node_spec
            
        for node in self.nodes:
            if len(self.children[node])>0:
                self.nodes[node]["children"] = self.children[node]
            else:
                self.nodes[node]["children"] = None
                
        # certainty scaling
        self.event_caution = 0.0
        
        og = OrderedSkeleton()
        og.V = self.nodes.keys()
        edges = []
        for k,children in self.children.iteritems():
            for child in children:
                edges.append((k, child))
        
        og.E = edges
        og.toporder()
             
        nd = NodeData()
        nd.Vdata = self.nodes
        
        logging.debug(pprint.pformat(nd.Vdata))
        
        self.net = DiscreteBayesianNetwork(og, nd)
        self.factor_net = TableCPDFactorization(self.net)
        
            
        
        
    def infer(self, sensor_evidence, fsm_evidence):
        
        
        # sensor values are always True; their proxy nodes encode the real probability
        evidence = dict(fsm_evidence)
        evidence.update({k:"T" for k in sensor_evidence})
        
        # update probability of proxy nodes
        for sensor,p in sensor_evidence.iteritems():
            self.net.Vdata[sensor]["cprob"] = {"['T']":[p, 1-p], "['F']":[(1-p),p]}
                
        # refactorize
        fn = TableCPDFactorization(self.net)
        events = []
        
        for name,output in self.outputs.iteritems():
            fn.refresh()
            query = {}
            
            for q in output["query"]:
                if is_negated(q):
                   query[normalise_name(q)] = ['F']
                else:
                    query[normalise_name(q)] = ['T']
            
            prob = result = fn.specificquery(query, evidence)
            ev = output["event"]
            formatted_query = " AND ".join(query)
            logging.debug("Query p(%s)=%.8f; need p(%s)>%.8f to trigger event %s/%s" % (formatted_query, prob, formatted_query, 1-np.exp(ev["logp"]), ev.get("fsm", None), ev["event"]))
            if prob>(1-np.exp(ev["logp"]))+self.event_caution:
                logging.debug("Fired event %s/%s" % (ev.get("fsm", None), ev["event"]))
                # generate event
                events.append({"fsm":ev.get("fsm", None), "event":ev["event"]})
        
        return events
        
        
    def update_nodes(self, prob_dict):
        for node,p in prob_dict.iteritems():
            vdata = {}
            vdata["numoutcomes"] = 2
            vdata["vals"] = ["True", "False"]
            vdata["parents"] = None # these are known values
            vdata["children"] = self.find_children(node)            
            vdata["cprob"] = [p,1-p] # direct probability
            libpgm.CPDtypes.discrete.Discrete(vdata)
        
    
    def add_to_graph(self, graph, prefix=""):
        bnet = pydot.Cluster("BayesNet", label="Bayes Net", 
                                fontname="helvetica",
                                color="gray", fontcolor="gray")
        graph.add_subgraph(bnet)
        node_mapping = {}
        bg_colors = {"fsm_input":"gray", "sensor_input":"yellow", "output":"lightblue", "inferred":"white"}
        
        fsm_inputs = {}
        sensor_inputs = {}
        # nodes
        for name, node in self.nodes.iteritems():
            if node["type"]!="proxy":
                bg_color = bg_colors[node["type"]]
                bel_node = pydot.Node(name=prefix+name, shape="ellipse", label=name, fillcolor=bg_color, style="filled")
                if node["type"]=="fsm_input":
                    fsm_inputs[name] = bel_node
                if node["type"]=="sensor_input":
                    sensor_inputs[name] = bel_node
                    
                bnet.add_node(bel_node)
                node_mapping[name] = bel_node
        
        # edges
        for name, node in self.nodes.iteritems():           
            if node["type"]!='proxy':
                children = self.children.get(name, [])
                for child in children:
                    child_edge = pydot.Edge(node_mapping[name], node_mapping[child])
                    bnet.add_edge(child_edge)
        # outputs
        outputs = {}
        for name, output in self.outputs.iteritems():
            bel_node = pydot.Node(name=name, shape="ellipse", label=name, fillcolor="lightblue", style="filled")
            bnet.add_node(bel_node)          
            
            for q in output["query"]:
                qname = normalise_name(q)
                edge = pydot.Edge( node_mapping[qname], bel_node, style="dashed")
                bnet.add_edge(edge)
            ev = output["event"]
            outputs[name] = {"node":bel_node, "fsm":ev["fsm"], "event":ev["event"]}
        return fsm_inputs, sensor_inputs, outputs
                
                
                   
            
            

    
def load_bayes_net(yaml_file):
    with open(yaml_file) as f:
        bayes_specs = yaml.load(f)
    bn = BayesNet(bayes_specs)
    return bn
if __name__=="__main__":    
    bn = load_bayes_net("demo_model/bayes_net.yaml")
    bn.infer({}, {"not_grasping":"F"})