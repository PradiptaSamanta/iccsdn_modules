import os 

_pythonpath = os.environ['PYTHONPATH']

_present_in_pythonpath =  _pythonpath.find('iccsdn_module') >= 0

if (_present_in_pythonpath):
  import CC
  import MP2
else:
  from pyscf.iccsdn import CC
  from pyscf.iccsdn import MP2

import pyscf
from pyscf import gto, scf

##---------------------------------------------------------##
             #Specify geometry and basis set#       
##---------------------------------------------------------##

mol = pyscf.gto.M(
verbose = 5,
output = None,
unit='Bohr',
atom ='''
Li  0.000000,  0.000000, -0.3797714041
H   0.000000,  0.000000,  2.6437904102
''',
basis = 'sto-3g',
#basis = 'cc-pVDZ',
symmetry = 'C2v',
)

##---------------------------------------------------------##

mf = scf.RHF(mol).run()

#mp2_res = MP2.MP2(mf)
#mp2_res.nfo = 1
#mp2_res.run()

cc_res = CC.state(mf)
cc_res.variant = 'CCSD'
if (cc_res.variant == 'ICCSD'):
    cc_res.no_act = 1
    cc_res.nv_act = 1

cc_res.maxsub = 7
#cc_res.conv = 1e-7
cc_res.maxiter = 50

cc_res.energy.run()

cc_res.maxiter = 30
cc_res.conv = 1e-6
cc_res.maxsub=40

cc_res.exc_en.root_info = [1,0,0,0]
cc_res.exc_en.run()

