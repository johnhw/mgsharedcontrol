import yaml
import fysom
import pydot
import os, sys, json
import config, logutil

# todo: mark events as "outgoing" to allow them to be captured and sent on

logger = logutil.get_logger('FSM')

class FSM(object):
    def __init__(self, name, spec):
        """
        Create an FSM from a collection of YAML specs
        """
        self.event_stack = []
        self.name = name
        initial = spec["initial"]
        events = spec["events"]        
        event_list = []
        for name, event_spec in events.iteritems():
            ev = dict(event_spec)
            ev["name"] = name            
            event_list.append(ev)
        fysom_spec = {'initial':initial, 'events':event_list}
        self.fsm = fysom.Fysom(fysom_spec, trace=True)

        logger.info("FSM '%s' created" % self.name)
        
        # attach event handlers
        for name, event_spec in events.iteritems():        
            if "before" in event_spec:
                self.fsm.__dict__['onbefore%s'%name] = lambda x,y=event_spec["before"]: self.fire_event(y)
            if "after" in event_spec:
                self.fsm.__dict__['onafter%s'%name] = lambda x,y=event_spec["after"]: self.fire_event(y)
            
        # attach state handlers
        if "state_callbacks" in spec:        
            self.state_callbacks = spec["state_callbacks"]
            
            for state, callbacks in self.state_callbacks.iteritems():                        
                if "enter" in callbacks:
                    self.fsm.__dict__['onenter%s'%state] =  lambda x,y=callbacks["enter"]: self.fire_event(y)
                  
                if "exit" in callbacks:
                    self.fsm.__dict__['onleave%s'%state] =  lambda x,y=callbacks["exit"]: self.fire_event(y)
                if "reenter" in callbacks:
                    self.fsm.__dict__['onreenter%s'%state] =  lambda x,y=callbacks["reenter"]: self.fire_event(y)
                
            
    def fire_event(self, ev):
        self.event_stack.append(ev)
        logger.info(json.dumps({'type': 'FSM_event', 'FSM': self.name, 'name': ev}))
        return True
        
    def clear_events(self):
        self.event_stack = []
        
    def states(self):
        return self.fsm._states
                
    def events(self):
        return self.fsm._events
        
    def event(self, event):
        if self.fsm.can(event):
            self.fsm.trigger(event)
            
class MultiFSM(object):
    """
    Contains/manages a collection of FSM objects, indexed by name
    """
    def __init__(self):
        self.fsms = {}
        
    def add_fsm(self, name, fsm):
        """
        Adds a named FSM to the collection
        """
        self.fsms[name]=fsm
        
    def broadcast(self, event):
        """
        Broadcasts the given event to all FSMs
        """
        for name,fsm in self.fsms.iteritems():            
            fsm.event(event)
            
    def send(self, fsm_name, event):
        """
        Send an event to a named FSM, or broadcast to all if fsm_name is None
        """
        if fsm_name is None:
            self.broadcast(event)
        else:
            self.fsms[fsm_name].event(event)
            
    def get_fsm(self, name):
        """
        Retrieve a named FSM object
        """
        return self.fsms[name]
        
    def get_events(self):
        """
        Returns a dict of all output events collected from each sub FSM
        """
        # collect together all output events
        all_events = {}
        for fsm_name,fsm in self.fsms.iteritems():
            all_events[fsm] = list(fsm.event_stack)
            fsm.clear_events()
        return all_events
            
            
    def all_state(self):
        """
        Returns a dict indicating the current state of each FSM
        """
        states = {}
        for name,fsm in self.fsms.iteritems():            
            states[name] = fsm.state
        return states
        
    def print_all_state(self):
        """
        Print the name and current state of each FSM
        """
        for name,fsm in self.fsms.iteritems():            
            print "%s: %s" % (name, fsm.state)
            
    def add_to_graph(self, graph, draw_callbacks=False, prefix=""):
        """
        Adds the FSM(s) to a pydot graph
        """
        fsms = pydot.Cluster("FSMs", label="FSMs", 
                                fontname="helvetica",
                                color="gray", fontcolor="gray")
        graph.add_subgraph(fsms)
        fsm_nodes = {}
        for name,fsm in self.fsms.iteritems():
            
            fsm_graph = pydot.Cluster(name,label=name, 
                                fontname="helvetica",
                                color="gray", fontcolor="gray")
            
            fsms.add_subgraph(fsm_graph)
                        
            label = pydot.Node(prefix+"_fsm_"+name, label=name, style="invis")
            fsm_graph.add_node(label)
            
            fsm_nodes[name] = label
            node_mapping = {}
            for state in fsm.states():
            
                if state!="none":
                    state_node = pydot.Node(name=prefix+state, shape="ellipse", label=state)
                    fsm_graph.add_node(state_node)
                    node_mapping[state] = state_node
                    fsm_nodes[(name, state)] = state_node
                    
                                                           
            for ev in fsm.events():
                src = ev["src"]
                dst = ev["dst"]
                name = ev["name"]
                
                if "before" in ev and draw_callbacks:
                    before = '<font color="orange">%s</font>' % ev["before"]
                else:
                    before = ""
                    
                if "after" in ev  and draw_callbacks:
                    after  = '<font color="orange">%s</font><br/>' % ev["after"]
                else:
                    after = ""

                    
                label = "<%s  <b>%s</b> %s>" % (before, name, after)
                
                transition_edge = pydot.Edge(node_mapping[src], node_mapping[dst], label=label)
                
                
                fsm_graph.add_edge(transition_edge)
            if draw_callbacks:
                for name,callback in fsm.state_callbacks.iteritems():                
                    if "enter" in callback:
                            node = pydot.Node(name=prefix+"_enter_"+name, shape="circle", style="invis")                    
                            fsm_graph.add_node(node)                                        
                            enter_edge = pydot.Edge(node, node_mapping[name], label=callback["enter"], style="dotted", fontcolor="blue")
                            fsm_graph.add_edge(enter_edge)                                
                    if "exit" in callback:
                            node = pydot.Node(name=prefix+"_exit_"+name, shape="circle", style="invis")                    
                            fsm_graph.add_node(node)                                        
                            exit_edge = pydot.Edge(node_mapping[name], node, label=callback["exit"], style="dotted", fontcolor="blue")
                            fsm_graph.add_edge(exit_edge)              
        return fsm_nodes
        
        
def load_fsms(yaml_file):
    """
    Read a series of state machines froma YAML file.
    The YAML file must be a dictionary of a FSM definitions.
    Returns a single MultiFSM object
    """
    if not os.path.exists(yaml_file):
        print('Error: file "%s" does not exist!' % yaml_file)
        sys.exit(-1)

    try:
        with open(yaml_file) as f:
            fsm_specs = yaml.load(f)
    except Exception, e:
        print('Error loading YAML FSM definition:')
        print('\t%s\n\t' % (e.problem, e.problem_mark))
        sys.exit(-1)

    multi_fsm = MultiFSM()

    for name, specs in fsm_specs.iteritems():
        multi_fsm.add_fsm(name, FSM(name, specs))
    return multi_fsm
    
    
if __name__=="__main__":

    multi_fsm = load_fsms("demo_model/fsms.yaml")
    multi_fsm.broadcast("grasp")
    multi_fsm.broadcast("grasp_complete")
    
    ## write out image of this fsm set
    dot_object = pydot.Dot(graph_name="main_graph",rankdir="LR", labelloc='b', 
                       labeljust='r', ranksep=1)
                       
    multi_fsm.add_to_graph(dot_object)
    dot_object.write_png("fsm_demo.png", prog="dot")
    
