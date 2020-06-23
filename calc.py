import pyscf
from pyscf import gto, scf
import MP2

##---------------------------------------------------------##
             #Specify geometry and basis set#       
##---------------------------------------------------------##

mol = pyscf.gto.M(
verbose = 5,
output = None,
#unit='Bohr',
atom ='''
Li  0.000000,  0.000000, -0.3797714041
H   0.000000,  0.000000,  2.6437904102
''',
basis = 'sto-3g',
symmetry = 'C2v',
)

##---------------------------------------------------------##

mf = scf.RHF(mol).run()

mp2_res = MP2.MP2(mf)
mp2_res.nfo = 1
mp2_res.run()

cc_res = cc.ccsd(mf)