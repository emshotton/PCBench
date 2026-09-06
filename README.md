# PCBench: A Dataset for Printed Circuit Board Routing
PCBench is a dataset for PCB routing task, it includes a dataset consisting of 164 printed circuit boards (PCB), a data augmentation script  to expand the dataset for supervised learning (SL) tasks, and a reinforcement learning (RL) environment.
  
 
## Dataset
### Folder Structure
All the PCB designs in our dataset are stored in the folder `PCBs`, where each PCB design is stored in a subfolder named `{author/org}_{PCB_name}_{design_version(optional)}`. Below is the folder structure of the dataset.
```
├── PCBs
│   ├── master_metadata.json
│   ├── subfolder1
│   │   ├── raw.kicad_pcb
│   │   ├── processed.kicad_pcb
│   │   ├── final.json
│   │   ├── metadata.json
│   │   ├── visual.png
│   ├── subfolder2
│   │   ├── raw.kicad_pcb
│   │   ├── processed.kicad_pcb
│   │   ├── final.json
│   │   ├── metadata.json
│   │   ├── visual.png
│   ├── ...
```
The `raw.kicad_pcb` is the raw PCB design file, `process.kicad_pcb` is the file after cleaning up, `final.json` stores only  routing-related information used for ML tasks. `metadata.json` stores the meta information for each single PCB design. `visual.png` is a visualization of each single PCB design. `master_meta.json` contains metadata of all PCBs and global-level information.

### PCB Routing Description Language (PCB-RDL)
We propose a JSON specification (`final.json` for each PCB design) called the PCB Routing Description  Language (PCB-RDL) that expresses a PCB routing problem and its solutions intuitively using basic concepts in order to facilitate research into automated PCB routing using ML. Following figure shows is an example of PCB with marked components in PCB-RDL (Left) and it corrsponding PCB-RDL (Right).

![PCB example](https://github.com/PCBench/PCBench/blob/main/Images/PCB_example.png)

## Data Augmentation
### Run
The augmentation data can be generated with the script [`Scripts/Data_augmentation/augmentation.py`](https://github.com/PCBench/PCBench/blob/main/Scripts/Data_augmentation/augmentation.py).  To generate 3 samples by randomly extracting 50% nets from the PCB `1Bitsy_1bitsy`, please run the following command
```
cd Scripts/Data_augmentation/
python augmentation.py --num_samples 3 --net_ratio 0.5 --pcb_name 1Bitsy_1bitsy
```
### Output
All the generated PCBs will be stored in the folder named `augmented_data` under  `Scripts/Data_augmentation/`. In `augmented_data`, all the generated samples will be stored in a subfolder with the name of selected PCB. Each generated sample has the name `sample_index.json`. For example, the above command will generate the following file under `Scripts/Data_augmentation/`
```
├── augmented_data
│   ├── 1Bitsy_1bitsy
│   │   ├── 1.json
│   │   ├── 2.json
│   │   ├── 3.json
```

## RL environment

### Installation
The RL environment requires Python >= 3.7. You can simply install the environment with the following commands:
```
git clone https://github.com/PCBench/PCBench.git
cd PCBench
python setup.py install
```
After installation, open a Python console and type
```
from RLEnv.EnvLayer.PCBRoutingEnv import PCBRoutingEnv
```
If no error occurs, you have successfully installed the PCB routing environment.

### API Usage
The following content shows an example of API usage of PCBRoutingEnv. 
```
from RLEnv.EnvLayer.PCBRoutingEnv import PCBRoutingEnv
import random

resolution = [0.5, 0.5]
pcb_folder = '../PCBs/'
pcb_names = ["1Bitsy_1bitsy"]
iters = 30
env = PCBRoutingEnv(resolution=resolution, pcb_folder=pcb_folder, pcb_names=pcb_names)
obs, info = env.reset()
for _ in range(iters):
    act = random.randint(0,5)
    obs, rew, terminal, _, info = env.step(act)
    if terminal:
        env.reset()
```
You can find more examples of customizing functions of reward and state observation from [RLEnv/examples.ipynb](https://github.com/PCBench/PCBench/blob/main/RLEnv/examples.ipynb).

## Licensing

The code in this repository (scripts, the RL environment, notebooks) is released under the
MIT license in [`LICENSE`](LICENSE). **The boards under `PCBs/` are not.** Each board keeps
the license its authors chose, and each board folder records it:

- `metadata.json` → `licenses` holds the SPDX id, the license file's path in the source
  repository, the source commit the board was taken from, and a `status`:
  `licensed`, `licensed-unclassified` (a license file exists but could not be reduced to one
  SPDX id; read it), `unlicensed` (the source publishes no license), or `source-missing`
  (the source repository has since been deleted).
- `LICENSE` is the license text copied verbatim from the source repository.
- `NOTICE.md` carries the attribution (author, source, commit, retrieval date) and the
  modification statement required by CERN-OHL, the GPL family and the Creative Commons
  licenses: `processed.kicad_pcb` and `final.json` are derived from `raw.kicad_pcb` and stay
  under the source license.

Boards marked `unlicensed` are held for research and evaluation only. Their authors retain
all rights, and they must not be redistributed; [`LICENSES.md`](LICENSES.md) lists them
along with counts per license. `Scripts/Licensing/resolve_licenses.py` regenerates all of
the above from the source repositories.
