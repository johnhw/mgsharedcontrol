# Public API

The public API for the shared control model is very simple. No coding is required to build or modify a model. Only the specification of the model changes.

The class `SharedControl` represents a shared control object.

#### SharedControl
`init(model_dir)`

Load a model from the directory `model_dir`. There must be the following files in the `model_dir`: `bayes_net.yaml`, `encoder.yaml`, `fsms.yaml`.

`update(sensor_dict)`

 Takes a dictionary of `sensor_name:sensor_value` mappings.
 Returns a list of strings, representing all output events fired.

`render_graph(fname="shared_control_map.png`)

 Render the model as a graph.
 


# Model definition

## Model files
Each model file is a [YAML](http://yaml.org/) configuration file specifying the structure of the shared control model. 
 
A model has three parts:
* An **encoder**, specified by `encoder.yaml`, which transforms sensor vectors into probabilities of *boolean* states, for example the readings from an accelerometer into the probability that the arm is in the air. Multiple encoders can be attached to one sensor.
* A **finite state machine** collection, specified by `fsms.yaml`. This is a set of FSMs. Each FSM has a set of states, and transitions between them. Transitions in the FSM are triggered by the Bayes Net. The FSM can also feedback whether or not it is in a current state into the Bayes Net.

* A **Bayes net**, specified by `bayes_net.yaml`, which infers the probability of hidden states (e.g. the probability that the arm in a safe configuration, given whether it is gripping an object and whether it is on the table). It is a directed graph of nodes, each of which must either be true or false, but for some (the inferred nodes), the real value is unknown. The probability of a node is the degree to which we believe that state to be true. 

----

### Bayes net

The Bayes net has three kinds of nodes: 
* **input nodes** whose state is known for sure (e.g. the current state of a state machine), or for whom a specific probability is known (e.g. from a sensor encoder). 

* **inferred nodes** whose probability is determined from parent nodes, all the way back to input nodes.

* **output nodes** whose probability directly depends on probabilities of other nodes, and will send events to the FSMs. The output nodes are essentially queries on the Bayes Net: 
`if (the arm is up AND the arm is in a safe position) is true with probability 0.95 then tell the grasp FSM to begin releasing.`

The **encoder** feeds into the **Bayes net**, and the **FSMs** can also feed into the **Bayes Net**.

---

# Model file format

## encoder.yaml

Specifies encoders to be used, as table of sensor names to a list of encoder definitions. Every encoder maps from a sensor to a Bayes Net node.

    <sensor name>: 
        -         
        node: <node_name> 
        # <node_name> must match a node in the Bayes Net
        
        type: <type_name> 
        # type of encoder to use (see below)
        
        params: {params_dict} 
        # parameters of the encoder
        
        [flip:False]
        # flips the probabilities of this encoder if present and True
        
        [transform: {transform_dict}] 
        # transformation to apply to sensor before encoding
               

### Encoder types
The currently implemented encoders are:
#### threshold
A soft threshold.  True if sensor value > threshold, with a sigmoid transition.
##### arameters:
* `threshold`: value at which to switch from 0 to 1
* `softness`: softness of the transition. Higher is harder transition.

### range
A soft range (sigmoid on each side of a step). True if sensor value in range [left, right]
##### arameters:
* `left` left extent of range
* `right` 
* `left_softness`: softness of the left edge.
* `right_softness`: softness of the right edge. [optional will be equal to left_softness if omitted]

### gaussian
Unnormalised Gaussian. Exactly true at sensor = u, falloff given by sigma.
* `centre` mean of the distribution
* `witdth` std. dev. of the distribution

### binary
Transforms already binary inputs into uncertain ones. 
* `p` probability output if input is 1.0
* `no_p` probability output if inputs is 0.0
NB: does not enforce normalisation, but for most cases should have p==(1-no_p)

## recalibrate
*not merged into current version*
Recalibrates a probability output using a Gaussian Process. For example, to recalibrate SVM outputs to true trial likelihoods. 
* `calibration`: a calibration input file name
calibration files consist of lines of:
`classifier_probability true_label`

        0.653 1   
        0.210 1
        0.245 0
        0.655 1
        0.431 0


### Transforms
Transforms allow mapping multidimensional sensor inputs before passing to the encoders.
* `center` vector specifying centre to measure from
* `matrix` transform matrix to apply to centered values
* `norm` Minkowski norm to use (1=manhatten, 2=euclidean, etc.)

From a $k$ element vector $\bf{x}$, the transform outputs a single real value which is:
$$ \left(\sum_{i=0}^k [A(\bf{x}-\bf{c})]_i ^ n \right) ^ {-n} $$

For example:

    transform:
        center: [0,1,0]
        matrix: [[1,0,0],[0,2,0],[0,0,1]]
        norm: 2
would transform a 3D vector into a distance from [0,1,0], with the y-component scaled by a factor of 2.
## fsms.yaml
`fsms.yaml` describes a collection of state machines and event transitions.

    <machine_name>:
        initial: <initial_state>
        events:
             <event_name>:         
               src: <source_state>
               dst: <destination_state>
               [after: <event string to generate after transition>]
               [before: <event to generate before transition>]

        [state_callbacks:]    
              <state>:
                   [enter:  <event string to generate on enter state]
                   [exit:  <event string to generate on enter state]
                   [reenter: <event string to generate on re-entering state]

               
The strings specified in `after`, `before`, `enter`, `reenter` and `exit` will be generated as "external events" before/after transitions or on entering/exiting a state. These form the return values of `SharedControl.update()`

`state_callbacks` are optional. 

States do not need to be explictly listed; they are inferred from the event transitions.

The initial state of each machine must be given with the `initial` specifier.
            

## bayes_net.yaml


`bayes_net.yaml` describes the Bayes Net. The file is a dictionary of node names to node specifications:

    <node_name>:
        type: <node_type>
          
## Valid node types
`sensor_input`: probabilistic input from a sensor encoder. 
Requires no other specification. Must match a name of an output node in a sensor encoder.

`fsm_input`: boolean input from the finite state machine. The name is specified as `fsm/state`, where `fsm` is the machine and `state` is the specific state. This node is true if machine `fsm` is in state `state` and false otherwise. The node must refer to a valid state in the FSMs.

`inferred`: inferred from the state of other nodes in the network.
Such a node must specify:
`parents` a list of parent node names
`p` a conditional probability table. The format of this is as a probabilistic truth table. Each entry in the table is a string of f (for false) or t (for true). There must be one t or f for each parent. The order of the parents in the `parents` list must match the order of the string. For example if a node "alive?" had parents "breathing?" and "pulse?", then it would look like:

    alive?: 
        type: inferred
        parents:
            - pulse?
            - breathing?
        p:
            # very likely to be dead if no pulse and not breathing 
            ff : 0.01 
            # breathing but no pulse -- unlikely to be alive
            ft : 0.05 
            # pulse but no breathing -- probably alive
            tf : 0.7
            # definitely alive if pulse and breathing
            tt : 1.0

Note that all nodes are boolean, and so only the probability of the node being true is specified.

`output`: a query node conditioned on some evidence.  queried on the conjunction of the variables specified. Query cannot include other output nodes. `output` nodes must have a `query` and `event` entry.
`query` gives a list of inferred/input nodes. The probability of the query is the product of the probability of these nodes.
`event` gives the event to send to an FSM, and the probability threshold at which to do this. The probability is given as `logp`; the actual probability threshold used is `1-exp(logp)` (i.e. the log probability of not p).
for example:
    do_cpr:
        type:output
        query:
            - ~breathing?
            - no_dnr
        event:
            fsm: cpr
            event: start
            logp: -3
            
This would trigger the `start` transition in the `cpr` FSM if `(NOT breathing AND no_dnr)` was more likely than 95.02%

## Negation
Variables can be negated by introducing a ~ in front of the name. This is valid in queries and in the parents specification of an inferred node

# Example
The following model implements this graph:
<img src="shared_control_map_v.png" width="500px">


## bayes_net.yaml

        shoulder_jerked: 
            type: sensor_input

        gripped:
            type: sensor_input

        hand/not_grasping:
            type: fsm_input


        grasp?:
            type: inferred
            parents: 
                - gripped
                - shoulder_jerked
                - hand/not_grasping
            p:
                ttt : 0.9
                ttf : 0.1
                tft : 0.1
                tff : 0.01
                ftt : 0.0
                ftf : 0.0
                fft : 0.0
                fff : 0.0

        send_grasp:
            type: output
            query: 
                - grasp?
            event:
                fsm: hand
                event: grasp
                logp: -2
        
## fsms.yaml


    hand:
        initial: not_grasping

        events:
            grasp: 
                src: not_grasping
                dst: grasp_opening
                after: fes_grasp

            release:
                src: grasping
                dst: grasp_closing
                after: fes_release

            grasp_complete:
                src: grasp_opening
                dst: grasping

            release_complete:
                src: grasp_closing
                dst: not_grasping


        state_callbacks:            
            not_grasping:
                enter: fes_disable
            

## encoder.yaml        

    
    pressure:
        - node:  gripped
          type:  threshold
          params: { threshold: 0.5 }  
          flip: True            
          transform: {matrix:[-1], centre:[0]}


    shoulder_acc:
        - node:  shoulder_jerked
          type:  threshold
          params: { threshold: 0.5 }  
            
