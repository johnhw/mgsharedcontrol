import yaml
import fsm
import bayes_net
import sensor_encoder
import os, sys, json
import pydot
import config, logutil

logger = logutil.get_logger('SHARED')

class SharedControl(object):

    def __init__(self, model_dir):        
        self.fsms = fsm.load_fsms(os.path.join(model_dir, "fsms.yaml"))
        self.bayes_net = bayes_net.load_bayes_net(os.path.join(model_dir, "bayes_net.yaml"))
        self.sensor_encoder = sensor_encoder.load_sensor_encoder(os.path.join(model_dir, "encoder.yaml"))
        
    def update(self, sensor_dict):
        """
        Takes a dictionary of sensor_name:sensor_value mappings.
        Returns a list of strings, representing all output events fired.
        """
        # encode sensor values
        # get a node name->probability mapping
        sensor_probs = self.sensor_encoder.encode(sensor_dict)      
        logger.info(json.dumps({'type': 'sensor_update', 'value': '%s' % sensor_probs}))
        
        fsm_evidence = {}
        
        # infer bayes net output variables
        events = self.bayes_net.infer(sensor_probs, fsm_evidence)
        logger.info(json.dumps({'type': 'inferred_events', 'value': '%s' % events}))

        # trigger messages to the FSM (will be list of (fsm_name, event_name) pairs))
        # if fsm_name is None, this is a broadcast event        
        for event in events:
            logger.info(json.dumps({'type': 'send_FSM_event', 'value': event['event'], 'fsm': event['fsm']}))
            self.fsms.send(event["fsm"], event["event"])
            
        all_events = self.fsms.get_events()
        return list(all_events.values())
            
    def render_graph(self, fname="shared_control_map.png"):
        dot_object = pydot.Dot(graph_name="main_graph",rankdir="LR", labelloc='b', 
                       labeljust='r', ranksep=1)
                       
        dot_object.set_node_defaults(shape='circle', fixedsize='false',
                             height=.85, width=.85, fontsize=24, fontname="helvetica")
                             
        dot_object.set_edge_defaults(fontname="helvetica")
        dot_object.set_graph_defaults(fontname="helvetica")
                             

        target_nodes = self.sensor_encoder.add_to_graph(dot_object, prefix="sensor_")
        fsm_nodes = self.fsms.add_to_graph(dot_object, prefix="fsm_")
        fsm_inputs, sensor_inputs, outputs = self.bayes_net.add_to_graph(dot_object, prefix="bayes_")
        
        # bayes net -> fsm
        for name,output in outputs.iteritems():
            target_fsm = output["fsm"]
            output_node = output["node"]
            fsm_node = fsm_nodes[target_fsm]
            edge_label = output["event"]
            edge = pydot.Edge(output_node, fsm_node, style="dashed", label=edge_label, color="blue")
            dot_object.add_edge(edge)
        
        # fsm -> bayes net
        for name,input in fsm_inputs.iteritems():
            fsm, state = name.split('/')            
            in_node = fsm_nodes[(fsm, state)]
            out_node = input
            edge = pydot.Edge(in_node, out_node, style="dashed", color="blue")
            dot_object.add_edge(edge)
                    
        # sensor_encoder -> bayes net
        for target,target_node in target_nodes.iteritems():
            bn_node = sensor_inputs[target] 
            edge = pydot.Edge(target_node, bn_node, style="dashed")
            dot_object.add_edge(edge)
            
        import cPickle
        print(len(cPickle.dumps(dot_object)))
        dot_object.write_png(fname, prog="dot")
    
if __name__=="__main__":
    s = SharedControl("demo_model")             
    s.render_graph()
    events = s.update({"pressure":0.5, "shoulder_acc":251.0})
    print('Shared control events:', events)
