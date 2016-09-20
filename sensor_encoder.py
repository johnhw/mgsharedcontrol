import numpy as np
import yaml
from collections import defaultdict
import pydot
import logging

class Encoder(object):
    def __init__(self, sub_encoder, transform=None, flip=False):
        self.transform = transform
        self.flip = flip
        self.encoder = sub_encoder
        
        
    def encode(self, values):
        """Encode transforms a sensor vector into a single probability"""

        # make sure this is a one-d numpy array
        values = np.array(values).ravel()
        
        if self.transform==None:
            # univariate case
            p = self.encoder.prob(values[0])
        else:
            # multivariate transform
            p = self.encoder.prob(self.transform.transform(values))
            
            
        if self.flip:
            return 1-p
        else:
            return p
            
    def get_label(self):
        label = self.encoder.get_label()
        if self.flip:
            label = "~%s" % label
        return label
       
        
def norm(x, l):
    return np.sum(x**l)**(1.0/l)
    
def sigmoid(x):
    return 1 / (1+np.exp(-x))
    
def soft_threshold(x, t, softness=1.0):
    return sigmoid((x-t)*softness)
    
def soft_range(x, t1, t2, left_softness=1.0, right_softness=None):
    if right_softness is None:
        right_softness = left_softness    
    return soft_threshold(x,t1, left_softness) * (1.0-soft_threshold(x,t2, right_softness))
    
def gaussian(x, sigma):
    return np.exp(-(x**2)/(sigma**2))
    
class ThresholdEncoder(Encoder):
        def __init__(self, threshold, softness=1.0):
            self.softness = softness
            self.threshold = threshold

        def prob(self, values):
            return soft_threshold(values, self.threshold, self.softness)
            
        def get_label(self):            
            return "t=%.4f /=%.3f" % (self.threshold, self.softness)
            
            
class RangeEncoder(Encoder):
        def __init__(self, left, right, left_softness=1.0, right_softness=None):
            self.left = left
            self.right = right
            self.left_softness = left_softness
            self.right_softness = right_softness
  
            
        def prob(self, values):
            return soft_range(values, self.left, self.right, self.left_softness, self.right_softness)
            
        def get_label(self):
            return "[%.4f, %.4f] /=%.3f =\%.3f" % (self.left, self.right, self.left_softness, self.right_softness)
                                
            
class GaussianEncoder(Encoder):
        def __init__(self, centres, widths):
            self.centres = centres
            self.widths = widths
                
        def prob(self, values):
            return gaussian(values-self.centres, self.widths)
            
        def get_label(self):
            return "u=%.4f s=%.4f" % (self.centres, self.widths)
        
class BinaryEncoder(Encoder):
        def __init__(self, p, no_p=0):
            self.p = p
            self.no_p = no_p
                            
        def prob(self, values):
            if values>0.5:
                return self.p
            else:
                return self.no_p
                
        def get_label(self):
            return "p=%.4f" % (self.p)

# transform a vector into a distance
# if you need a multi-dimensional input, centre must be specified (even if it is just [0,0,0,...])

class Multivariate(object):
    def __init__(self, centre=None, matrix=None, norm=2):
            self.centre = centre
            self.norm = norm
            self.matrix = matrix
            
            if centre==None:
                centre = np.array([0])
            else:   
                centre = np.array(centre)
                
            if self.matrix is None:
                self.transform = np.eye(len(self.centre))
            else:
                self.matrix = np.array(matrix)
    
    def transform(self, values):
        return norm(np.dot(values-self.centre, self.matrix), self.norm)
                                          
class SensorEncoder(object):

    def __init__(self): 
        self.sensors = defaultdict(list)
    
    def add_encoder(self, sensor, target, encoder):
        self.sensors[sensor].append((target, encoder))
        
    def encode(self, sensor_dict):
        nodes = {}
        for sensor, vector in sensor_dict.iteritems():
            vector = np.array(vector)
            if sensor in self.sensors:
                for target, encoder in self.sensors[sensor]:
                    p = encoder.encode(vector)
                    logging.debug("P> %s=%s p(%s)=%.8f" % (sensor, vector, target, p))
                    if target not in nodes:
                        nodes[target] = p
                    else:
                        # can't write to the same target node twice -- this is meaningless
                        raise ValueError()
        return nodes
        
    def get_targets(self):
        return [t[0] for t in self.sensors]
        
    def add_to_graph(self, graph, draw_callbacks=False, prefix=""):
        target_nodes = {}
        encoders = pydot.Cluster("encoders", label="Sensor Encoders", 
                                fontname="helvetica",
                                color="gray", fontcolor="gray")
        graph.add_subgraph(encoders)
        for name, target_encoders in self.sensors.iteritems():
            sensor_node = pydot.Node(name=prefix+name, label=name, shape="diamond", fillcolor="/set310/1", style="filled")
            encoders.add_node(sensor_node)

            for target_encoder in target_encoders:
                target, encoder = target_encoder
                encoder_type = type(encoder.encoder).__name__
                encoder_label = "<%s<br/>%s>" % (encoder_type, encoder.get_label())
                encoder_node = pydot.Node(name=prefix+target+encoder_type, label=encoder_label, shape="rectangle", style="filled", fillcolor="/set310/2")
                
                encoders.add_node(encoder_node)
                b_node = pydot.Node(name=prefix+target, label=target, shape="ellipse", style="filled", fillcolor="/set310/3")
                encoders.add_node(b_node)
                encoders.add_edge(pydot.Edge(encoder_node, b_node))
                encoders.add_edge(pydot.Edge(sensor_node, encoder_node))
                target_nodes[target] = b_node
                
        return target_nodes
                            


    
def load_sensor_encoder(yaml_file):
    with open(yaml_file) as f:
        sensor_specs = yaml.load(f)
        
    encoder_types = {"gaussian":GaussianEncoder, "range":RangeEncoder, "threshold":ThresholdEncoder}
    sensor_encoder = SensorEncoder()
    for sensor, encoders in sensor_specs.iteritems():        
        for encoder in encoders:
            # target name
            target_node = encoder["node"]
            # transform
            transform = encoder.get("transform", None)
            
            if transform is not None:
                transform = Multivariate(**transform)
            
            # construct an encoder of the right type, with the specified parameters    
            encoder_type = encoder["type"]
            encoder_obj = encoder_types[encoder_type](**encoder["params"])            
            flip = encoder.get("flip", False)
            
            sensor_encoder.add_encoder(sensor, target_node, Encoder(encoder_obj, flip=flip, transform=transform))
    return sensor_encoder
    
                
def test_probability():
    import matplotlib.pyplot as plt
    import numpy
    x = np.linspace(0,1,100)
    plt.title("Threshold encoder, 0.5")
    for i in range(5):
        r = ThresholdEncoder(0.5, softness=i*5+1)    
        plt.plot(x, [r.prob(xi) for xi in x])
    plt.ylabel("p(x)")
    plt.xlabel("x")
    
    plt.figure()
    plt.title("Range encoder, [0.25, 0.75]")
    for i in range(5):
        r = RangeEncoder(0.25, 0.75, left_softness=i*5+1)    
        plt.plot(x, [r.prob(xi) for xi in x])
    plt.ylabel("p(x)")
    plt.xlabel("x")
            
    plt.figure()
    plt.title("Gaussian encoder, centre=0.5")
    for i in range(5):
        r = GaussianEncoder(0.5, i*0.1)    
        plt.plot(x, [r.prob(xi) for xi in x])
    plt.ylabel("p(x)")
    plt.xlabel("x")
    
        
    plt.show()
    
if __name__=="__main__":

    encoder = load_sensor_encoder("demo_model/encoder.yaml")
    print encoder.encode({"arm_distance":0.4})
    
     
    ## write out image of this fsm set
    dot_object = pydot.Dot(graph_name="main_graph",rankdir="LR", labelloc='b', 
                       labeljust='r', ranksep=1)
                           
    encoder.add_to_graph(dot_object)
    dot_object.write_png("encoder_demo.png", prog="dot")
    
    
    ## test probability plots
    # test_probability()
