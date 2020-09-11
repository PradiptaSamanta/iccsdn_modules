import numpy as np
import copy as cp
import scipy
import math

import pyscf
from pyscf import gto, scf
from pyscf.lib import logger

from PostHF import GetIntNData

import utils


class state():

    def __init__(self, mf, variant = 'CCSD', nfo=0, nfv=0):

        self.mol  = mf.mol
        self.mf = mf

        self.nfo = nfo
        self.nfv = nfv

	self.nel = self.mol.nelectron

	self.e_hf = mf.e_tot

	self.variant = variant
	self.tInitParams = True
	self.tdiis = True
	
	self.no_act = 0
	self.nv_act = 0
	
	self.maxiter = 50
	self.max_diis = 20
	self.conv = 1e-7

	self.energy = self.Energy(self)
	self.exc_en = self.Exc_en(self)

    def init_parameters(self):
	
	self.rank_So = 0
	self.rank_Sv = 0
	if (self.variant == 'LCCD'):
	    self.rank_t1 = 0
	    self.rank_t2 = 1
	    self.rank_t_max = 1 # This rank is defined as max(rank_t1,rank_t2)
	    print '**** RUNNING LCCD ****'
	elif (self.variant == 'CCD'):
	    self.rank_t1 = 0
	    self.rank_t2 = 2
	    self.rank_t_max = 2
	    print '**** RUNNING CCD ****'
	if (self.variant == 'LCCSD'):
	    self.rank_t1 = 1
	    self.rank_t2 = 1
	    self.rank_t_max = 1
	    print '**** RUNNING LCCD ****'
	elif (self.variant == 'CCSD'):
	    self.rank_t1 = 4
	    self.rank_t2 = 2
	    self.rank_t_max = 4
	    print '**** RUNNING CCSD ****'
	elif (self.variant == 'ICCSD'):
	    self.rank_t1 = 4
	    self.rank_t2 = 2
	    self.rank_So = 1
	    self.rank_Sv = 1
	    self.rank_t_max = 4
	    print '**** RUNNING ICCSD ****'

	self.tInitParams = False
	self.e_old = self.e_hf

    def initialize(self):

	self.AllData = GetIntNData(self.mf, self.nfo, self.nfv)

	self.AllData.transform_all_ints()

	self.twoelecint_mo = self.AllData.twoelecint_mo

	self.nao = self.AllData.nao
	self.nocc = self.AllData.nocc
	self.nvirt = self.AllData.nvirt

	self.AllData.no_act = self.no_act
	self.AllData.nv_act = self.nv_act

        if self.tInitParams:
            self.init_parameters()
 
	self.AllData.get_orb_sym()

    class Energy():

        def __init__(self, cc_main):
	    self.cc_main = cc_main

        def init_amplitudes(self, cc, data):
 
            data.init_guess_t2()
 
            if (cc.rank_t1 > 0):
                data.init_guess_t1()
 
            if (cc.rank_So > 0):
                data.init_guess_So()
 
            if (cc.rank_Sv > 0):
                data.init_guess_Sv()
 
            data.get_tau(cc.rank_t1)
 
 
        def init_diis(self, cc, data):
 
            if (cc.rank_t1 > 0):
                data.init_diis_t1()
 
            if (cc.rank_t2 > 0):
                data.init_diis_t2()
 
            if (cc.rank_So > 0):
                data.init_diis_So()
 
            if (cc.rank_Sv > 0):
                data.init_diis_Sv()
 
            data.diis_errors = []
 
        def update_diis(self, cc, data, x):
 
            # Limit size of DIIS vector
            if (len(data.diis_vals_t2) > cc.max_diis):
                if (cc.rank_t1 > 0):
                    del data.diis_vals_t1[0]
                if (cc.rank_t2 > 0):
                    del data.diis_vals_t2[0]
                if (cc.rank_So > 0):
                    del data.diis_vals_So[0]
                if (cc.rank_Sv > 0):
                    del data.diis_vals_Sv[0]
                del data.diis_errors[0]
            self.diis_size = len(data.diis_vals_t2) - 1
 
            # Build error matrix B, [Pulay:1980:393], Eqn. 6, LHS
            ci = data.diis_error_matrix(self.diis_size)
            # Calculate new amplitudes
            if (x+1) % cc.max_diis == 0:
                if (cc.rank_t1 > 0):
                    data.update_diis_t1(self.diis_size)
                if (cc.rank_t2 > 0):
                    data.update_diis_t2(self.diis_size)
                if (cc.rank_So > 0):
                    data.update_diis_So(self.diis_size)
                if (cc.rank_Sv > 0):
                    data.update_diis_Sv(self.diis_size)
 
            # End DIIS amplitude update
        
 
        def energy_cc(self, cc, data):
            occ = data.nocc
            nao = data.nao
            e_cc  = 2*np.einsum('ijab,ijab',data.t2,data.twoelecint_mo[:occ,:occ,occ:nao,occ:nao]) 
            e_cc += -np.einsum('ijab,ijba',data.t2,data.twoelecint_mo[:occ,:occ,occ:nao,occ:nao])
            if (cc.rank_t1 > 0):
                e_cc += 2*np.einsum('ijab,ia,jb',data.twoelecint_mo[:occ,:occ,occ:nao,occ:nao],data.t1,data.t1) 
                e_cc += - np.einsum('ijab,ib,ja',data.twoelecint_mo[:occ,:occ,occ:nao,occ:nao],data.t1,data.t1)
            return e_cc
 
        def convergence(self, cc, e_cc, eps, x):
            del_e = e_cc - cc.e_old
            if abs(eps) <= cc.conv and abs(del_e) <= cc.conv:
                print "ccsd converged!!!"
                print "Total energy is : "+str(cc.e_hf + e_cc)
                return True
            else:
                print "cycle number : "+str(x+1)
                print "change in t1 and t2 : "+str(eps)
                print "energy difference : "+str(del_e)
                print "energy : "+str(cc.e_hf + e_cc)
                return False
 
        def convergence_ext(self, cc, e_cc, eps, eps_So, eps_Sv, x):
            del_e = e_cc - cc.e_old
            if abs(eps) <= cc.conv and abs(eps_So) <= cc.conv and abs(eps_Sv) <= cc.conv and abs(del_e) <= cc.conv:
                print "change in t1+t2 , So, Sv : "+str(eps)+" "+str(eps_So)+" "+str(eps_Sv)
                print "energy difference : "+str(del_e)
                print "ccsd converged!!!"
                print "Total energy is : "+str(cc.e_hf + e_cc)
                return True
            else:
        	print "cycle number : "+str(x+1)
                print "change in t1+t2 , So, Sv : "+str(eps)+" "+str(eps_So)+" "+str(eps_Sv)
                print "energy difference : "+str(del_e)
                print "energy : "+str(cc.e_hf + e_cc)
                return False
 
        def calc_residue(self, cc, data):
 
            intermediates = utils.intermediates(data)
            amplitude = utils.amplitude(data)

            # First get all the intermediates
            I_vv, I_oo, Ivvvv, Ioooo, Iovvo, Iovvo_2, Iovov,Iovov_2 = intermediates.initialize()
            if (cc.rank_t2 > 1):
                I_oo,I_vv,Ioooo,Iovvo,Iovvo_2,Iovov = intermediates.update_int(I_vv,I_oo,Ioooo,Iovvo,Iovvo_2,Iovov)
 
            if (cc.rank_t1 > 0):
                I1, I2 = intermediates.R_ia_intermediates()
 
            if (cc.rank_So > 0):
                II_oo = intermediates.W1_int_So()
                II_vv = intermediates.W1_int_Sv()
                II_ov = intermediates.coupling_terms_So()
                II_vo = intermediates.coupling_terms_Sv()
 
                II_ovoo,II_ovoo3,II_vvvo3 = intermediates.W2_int_So()
                II_vvvo,II_vvvo2,II_ovoo2 = intermediates.W2_int_Sv()
 
            if (cc.rank_t1 > 0):
                self.R_ia = amplitude.singles(I1,I2,I_oo,I_vv)
                I_oo,I_vv,I_oovo,I_vovv,Ioooo_2,I_voov,Iovov_3,Iovvo_3,Iooov,I3=intermediates.singles_intermediates(I_oo,I_vv,I2, cc.rank_t1)
 
            self.R_ijab = amplitude.doubles(I_oo,I_vv,Ivvvv,Ioooo,Iovvo,Iovvo_2,Iovov,Iovov_2)
 
            if (cc.rank_t1 > 0):
                self.R_ijab += amplitude.singles_n_doubles(I_oovo,I_vovv, cc.rank_t1)
                self.R_ijab += amplitude.higher_order(Iovov_3, Iovvo_3, Iooov, I3, Ioooo_2, I_voov, cc.rank_t1)
 
            if (cc.rank_So > 0):
                self.R_ijab += amplitude.inserted_diag_So(II_oo) 
 
                self.R_ijav = amplitude.So_diagram_vs_contraction()
                self.R_ijav += amplitude.So_diagram_vt_contraction()
                self.R_ijav += amplitude.v_sv_t_contraction_diag(II_vo)
                self.R_ijav += amplitude.w2_diag_So(II_ovoo,II_vvvo2,II_ovoo2)
                if (cc.rank_t1 > 0):
                    self.R_ijav += amplitude.T1_contribution_So()
                    self.R_ia += amplitude.inserted_diag_So_t1(II_oo)
 
            if (cc.rank_Sv > 0):
                self.R_ijab += amplitude.inserted_diag_Sv(II_vv) 
 
                self.R_iuab = amplitude.Sv_diagram_vs_contraction()
                self.R_iuab += amplitude.Sv_diagram_vt_contraction()
                self.R_iuab += amplitude.v_so_t_contraction_diag(II_ov)
                self.R_iuab += amplitude.w2_diag_Sv(II_vvvo,II_ovoo3,II_vvvo3)
                if (cc.rank_t1 > 0):
                    self.R_iuab += amplitude.T1_contribution_Sv()
                    self.R_ia += amplitude.inserted_diag_Sv_t1(II_vv)
        
 
            self.R_ijab = data.symmetrize(self.R_ijab)
 
        def update_amplitudes(self, cc, data):
 
            if (cc.rank_t2 > 0 and cc.rank_t1 > 0):
                self.eps = data.update_t1_t2(self.R_ia, self.R_ijab)
            else:
                self.eps = data.update_t2(self.R_ijab)
 
            if (cc.rank_So > 0):
                self.eps_So = data.update_So(self.R_ijav)
 
            if (cc.rank_Sv > 0):
                self.eps_Sv = data.update_Sv(self.R_iuab)
 
            
        def converge_cc_eqn(self, cc, data):
 
            for x in range(0, cc.maxiter):
 
                data.get_tau(cc.rank_t1)
                self.calc_residue(cc, data)
 
                self.update_amplitudes( cc, data)
                if ((x+1) > cc.max_diis) and cc.tdiis:
            	    self.update_diis(cc, data, x)
 
                e_cc = self.energy_cc(cc, data)
 
                if (cc.rank_So > 0):
                    val = self.convergence_ext(cc, e_cc,self.eps, self.eps_So, self.eps_Sv, x)
                else: 
                    val = self.convergence(cc, e_cc,self.eps, x)
 
                if val == True :
                    break
                else:  
                    cc.e_old = e_cc
            
                if cc.tdiis:
                    if (cc.rank_t1 > 0):
                        errors_t1 = data.errors_diis_t1()
                    if (cc.rank_t2 > 0):
                        errors_t2 = data.errors_diis_t2()
                    if (cc.rank_So > 0):
                        errors_So = data.errors_diis_So()
                    if (cc.rank_Sv > 0):
                        errors_Sv = data.errors_diis_Sv()
            	
                if (cc.rank_t2 > 0 and cc.rank_t1 > 0):
                    data.diis_errors.append(np.concatenate((errors_t1,errors_t2)))
                else:
                    data.diis_errors.append((errors_t2))
 
        def run(self):
 
	    self.cc_main.initialize()
 
            self.init_amplitudes(self.cc_main, self.cc_main.AllData)

            if self.cc_main.tdiis:
                self.init_diis(self.cc_main, self.cc_main.AllData)
 
            self.converge_cc_eqn(self.cc_main, self.cc_main.AllData)

            print '**** CCSD is done ****'


    class Exc_en():
    
        def __init__(self, cc_main):

	    self.cc_main = cc_main
	    self.root_info = [1]
	    self.nDavidson = 40
            self.conv = cc_main.conv

        def init_all_data(self, cc, data, ind):

            self.init_amplitudes(cc, data, ind)
	    data.init_Y_mat(cc.rank_So, cc.rank_Sv)
	    data.init_B_mat(cc.rank_So, cc.rank_Sv,self.root_info[ind])
            self.count = [0]*self.root_info[ind]

        def init_amplitudes(self, cc, data, ind):
 
	    data.init_guess_r_t1_t2( ind, self.root_info[ind])

            if (cc.rank_So > 0):
                data.init_guess_r_So(self.root_info[ind])
 
            if (cc.rank_Sv > 0):
                data.init_guess_r_Sv(self.root_info[ind])
	    
	    print 'Response amplitudes are initiated'

        def calc_matrix_products(self, cc, data):

            intermediates = utils.intermediates_response(data, self.r, self.iroot)
            amplitude = utils.amplitude_response(data, self.r, self.iroot)

            I_vv, I_oo, Ivvvv, Ioooo, Iovvo, Iovvo_2, Iovov,Iovov_2 = intermediates.initialize()
            if (cc.rank_t1 > 0):
                data.dict_Y_ia[self.r, self.iroot] = amplitude.singles_linear(I_oo,I_vv)
            data.dict_Y_ijab[self.r, self.iroot] = amplitude.doubles_linear(I_oo,I_vv,Ivvvv,Ioooo,Iovvo,Iovvo_2,Iovov,Iovov_2, cc.rank_t1)

            if (cc.rank_t2 > 1):
                I_oo,I_vv,Ioooo,Iovvo,Iovvo_2,Iovov = intermediates.update_int(I_vv,I_oo,Ioooo,Iovvo,Iovvo_2,Iovov, order=0)
                I_oo_R,I_vv_R,Ioooo_R,Iovvo_R,Iovvo_2_R,Iovov_R = intermediates.update_int(I_vv,I_oo,Ioooo,Iovvo,Iovvo_2,Iovov, order=1)
 
                if (cc.rank_t1 > 1):
                    I1, I2 = intermediates.R_ia_intermediates(order=0)
                    I1_R, I2_R = intermediates.R_ia_intermediates(order=1)
                    data.dict_Y_ia[self.r, self.iroot] += amplitude.singles_quadratic(I_oo,I_vv,I1,I2,order=1)
                    data.dict_Y_ia[self.r, self.iroot] += amplitude.singles_quadratic(I_oo_R,I_vv_R,I1_R,I2_R,order=0)
                    data.dict_Y_ia[self.r, self.iroot] += amplitude.singles_coupled_order()
 
		I_oo,I_vv,Ioovo,Ivovv = intermediates.singles_intermediates(I_oo,I_vv, cc.rank_t1, order=0)
		I_oo_R,I_vv_R,Ioovo_R,Ivovv_R = intermediates.singles_intermediates(I_oo_R,I_vv_R, cc.rank_t1, order=1)

                data.dict_Y_ijab[self.r, self.iroot] += amplitude.doubles_quadratic(I_oo,I_vv,Ioooo,Iovvo,Iovvo_2,Iovov, order=1)
                data.dict_Y_ijab[self.r, self.iroot] += amplitude.doubles_quadratic(I_oo_R,I_vv_R,Ioooo_R,Iovvo_R,Iovvo_2_R,Iovov_R, order=0)

                if (cc.rank_t1 > 0):
                    data.dict_Y_ijab[self.r, self.iroot] += amplitude.singles_n_doubles(Ioovo,Ivovv, order=1)
                    data.dict_Y_ijab[self.r, self.iroot] += amplitude.singles_n_doubles(Ioovo_R,Ivovv_R, order=0)
                    if (cc.rank_t1 > 1):
                        data.dict_Y_ijab[self.r, self.iroot] += amplitude.singles_to_doubles()
	
                data.dict_Y_ijab[self.r, self.iroot] = data.symmetrize(data.dict_Y_ijab[self.r, self.iroot])

	def reshape_BMat(self, cc, data):

	    nroot = self.nroot
	    r = self.r
	    if (cc.rank_t1 > 0):
                B_Y_ia_nth = np.zeros((nroot*(r+1),nroot*(r+1)))
            B_Y_ijab_nth = np.zeros((nroot*(r+1),nroot*(r+1)))

            if (r == 0): 
	        if (cc.rank_t1 > 0):
                    B_Y_ia_nth[:nroot,:nroot] = data.B_Y_ia 
                B_Y_ijab_nth[:nroot,:nroot] = data.B_Y_ijab
            else: 
	        if (cc.rank_t1 > 0):
                    B_Y_ia_nth[:nroot*r,:nroot*r] = data.B_Y_ia 
                B_Y_ijab_nth[:nroot*r,:nroot*r] = data.B_Y_ijab

	    if (cc.rank_t1 > 0):
                data.B_Y_ia = cp.deepcopy(B_Y_ia_nth)
            data.B_Y_ijab = cp.deepcopy(B_Y_ijab_nth)
            
            B_Y_ia_nth = None
            B_Y_ijab_nth = None

	def form_BMat(self, cc, data):

	    r = self.r
	    nroot = self.nroot
            for m in range(0,r):
              for iroot in range(0,nroot):
                for jroot in range(0,nroot):
                  loc1 = r*nroot+iroot
                  loc2 = m*nroot+jroot
          
                  data.B_Y_ia[loc1,loc2] = 2.0*np.einsum('ia,ia',data.dict_r_t1[r,iroot],data.dict_Y_ia[m,jroot])
                  data.B_Y_ia[loc2,loc1] = 2.0*np.einsum('ia,ia',data.dict_r_t1[m,jroot],data.dict_Y_ia[r,iroot])
          
                  data.B_Y_ijab[loc1,loc2] = 2.0*np.einsum('ijab,ijab',data.dict_r_t2[r,iroot],data.dict_Y_ijab[m,jroot])-np.einsum('ijba,ijab',data.dict_r_t2[r,iroot],data.dict_Y_ijab[m,jroot])
                  data.B_Y_ijab[loc2,loc1] = 2.0*np.einsum('ijab,ijab',data.dict_r_t2[m,jroot],data.dict_Y_ijab[r,iroot])-np.einsum('ijba,ijab',data.dict_r_t2[m,jroot],data.dict_Y_ijab[r,iroot])
                  
            for iroot in range(0,nroot):
              for jroot in range(0,nroot):
                loc1 = r*nroot+iroot
                loc2 = r*nroot+jroot
   
                data.B_Y_ia[loc1,loc2] = 2.0*np.einsum('ia,ia',data.dict_r_t1[r,iroot],data.dict_Y_ia[r,jroot])
                data.B_Y_ijab[loc1,loc2] = 2.0*np.einsum('ijab,ijab',data.dict_r_t2[r,iroot],data.dict_Y_ijab[r,jroot])-np.einsum('ijba,ijab',data.dict_r_t2[r,iroot],data.dict_Y_ijab[r,jroot])
  
             
            B_total = data.B_Y_ia+data.B_Y_ijab
	    return B_total

	def select_vectors(self, w_total, vects_total):

          dict_coeff_total = {}
          w = []

	  r = self.r
	  nroot = self.nroot

          if(r == 0):
            self.dict_v_nth = {}
         
            for iroot in range(0,nroot):
              ind_min_wtotal = np.argmin(w_total)                          #to calculate the minimum eigenvalue location from the entire spectrum
              dict_coeff_total[iroot] = vects_total[:,ind_min_wtotal].real  #to calculate the coeff matrix from eigen function corresponding to lowest eigen value
              self.dict_v_nth[iroot] = dict_coeff_total[iroot]
              w.append(w_total[ind_min_wtotal])
              w_total[ind_min_wtotal] = 123.456
         
          else:
            S_k = {}
            for iroot in range(0,nroot):
              S_k[iroot] = np.zeros((len(w_total)))
              for k in range(0,len(w_total)):
                m = w_total.argsort()[k]
                vect_mth = vects_total[:,m].real
                S_k[iroot][m] = np.abs(np.linalg.multi_dot([self.dict_v_nth[iroot][:],vect_mth[:r*nroot]]))
         
              b = np.argmax(S_k[iroot])
              w.append(w_total[b])
              dict_coeff_total[iroot] = vects_total[:,b].real 
              self.dict_v_nth[iroot] = dict_coeff_total[iroot]
  
	  return w, dict_coeff_total

	def expand_vector_component(self, dict_t, nroot, r, n_ind, ind_dims):

	  dict_x_t = {}

	  for iroot in range(0,nroot):
	    if (n_ind == 4):
	      dict_x_t[iroot] = np.zeros((ind_dims[0],ind_dims[1],ind_dims[2],ind_dims[3]))
	    elif (n_ind == 2):
	      dict_x_t[iroot] = np.zeros((ind_dims[0],ind_dims[1]))
	    else: 
	      print 'Only possible for one- and two-body excitations'

	    for m in range(0,r+1):
	      loc = m*nroot+iroot
	      dict_x_t[iroot] += np.linalg.multi_dot([self.dict_coeff_total[iroot][loc],dict_t[m,iroot]])

	  return dict_x_t

        def find_norm(self, vec_t2, vec_t1=None, vec_So=None, vec_Sv=None):

	  norm = 2.0*np.einsum('ijab,ijab', vec_t2, vec_t2) - np.einsum('ijab,ijba', vec_t2, vec_t2)

	  try:
	    norm += 2.0*np.einsum('ia,ia', vec_t1, vec_t1)
	  except: 
	    norm += 0.0

	  try:
	    norm += 2.0*np.einsum('ijav,ijav',vec_So,vec_So) - np.einsum('ijav,jiav',vec_So,vec_So)
	    norm += 2.0*np.einsum('iuab,iuab',vec_Sv,vec_Sv) - np.einsum('iuab,iuba',vec_Sv,vec_Sv)
	  except:
	    norm += 0.0

          return norm

	def normalise_vector(self, vec_t2, vec_t1=None, vec_So=None, vec_Sv=None):

          norm = self.find_norm(vec_t2, vec_t1, vec_So, vec_Sv)
	  sqrt_norm = math.sqrt(norm)

	  if (sqrt_norm > 1e-12):
	    vec_t2 = vec_t2/sqrt_norm
	    try:
	      vec_t1 = vec_t1/sqrt_norm
	      try:
	        vec_So = vec_So/sqrt_norm
	        vec_Sv = vec_Sv/sqrt_norm
	        return vec_t2, vec_t1, vec_So, vec_Sv  
	      except:
	        vec_So = None
	        vec_Sv = None
	        return vec_t2, vec_t1
	    except:
	      vec_t1 = None
	      return vec_t2
          else:
            print 'Error in calculation: Generating vector with zero norm'
            quit()


	def expand_vector(self, cc, data):

	  nroot = self.nroot
	  r = self.r

	  self.dict_x_t2 = self.expand_vector_component(data.dict_r_t2, nroot, r, 4, [cc.nocc,cc.nocc,cc.nvirt,cc.nvirt])

	  if (cc.rank_t1 > 0):
	    self.dict_x_t1 = self.expand_vector_component(data.dict_r_t1, nroot, r, 2, [cc.nocc,cc.nvirt])

	  for iroot in range(0,nroot):
	    if (cc.rank_t1 >  0):
	      # The ordering of the arguments is important here
	      self.dict_x_t2[iroot], self.dict_x_t1[iroot] = self.normalise_vector(self.dict_x_t2[iroot], self.dict_x_t1[iroot])
              print self.dict_x_t2[iroot]
              print self.dict_x_t1[iroot]
	    else:
	      self.dict_x_t2[iroot] = self.normalise_vector(self.dict_x_t2[iroot])
            

	def calc_residue_component(self, dict_t, dict_Y_t, nroot, r, n_ind, ind_dims):

	  dict_R_t = {}

	  for iroot in range(0,nroot):
	    if (n_ind == 4):
	      dict_R_t[iroot] = np.zeros((ind_dims[0],ind_dims[1],ind_dims[2],ind_dims[3]))
	    elif (n_ind == 2):
	      dict_R_t[iroot] = np.zeros((ind_dims[0],ind_dims[1]))
	    else: 
	      print 'Only possible for one- and two-body excitations'

	    for m in range(0,r+1):
	      for jroot in range(0, nroot):
	        loc = m*nroot+jroot
	        dict_R_t[iroot] += self.dict_coeff_total[iroot][loc]*dict_Y_t[m,jroot] - self.w[iroot]*self.dict_coeff_total[iroot][loc]*dict_t[m,jroot]

	  return dict_R_t

	def calc_residue(self, cc, data):

	  nroot = self.nroot
	  r = self.r

	  self.dict_R_ijab = self.calc_residue_component(data.dict_r_t2, data.dict_Y_ijab, nroot, r, 4, [cc.nocc,cc.nocc,cc.nvirt,cc.nvirt])
	  if (cc.rank_t1 > 0):
	    self.dict_R_ia = self.calc_residue_component(data.dict_r_t1, data.dict_Y_ia, nroot, r, 2, [cc.nocc,cc.nvirt])

        def update_t1_t2(self, R_ia, R_ijab):
            ntmax = 0
            ntmax = np.size(R_ia)+np.size(R_ijab)
            eps = float(np.sum(abs(R_ia)+np.sum(abs(R_ijab)))/ntmax)
            return eps
  
        def update_t2(self, R_ijab):
            ntmax = 0
            ntmax = np.size(R_ijab)
            eps = float(np.sum(abs(R_ijab))/ntmax)
            return eps

	def check_convergence(self, cc, data):

          nroot = self.nroot

          eps_t = []
          
          if cc.rank_So > 0:
            eps_So = []
          if cc.rank_Sv > 0:
            eps_Sv = []

          for iroot in range(0, nroot):
            if(cc.rank_t1 > 0):      
	      eps_t.append(self.update_t1_t2(self.dict_R_ia[iroot], self.dict_R_ijab[iroot]))
            else: 
	      eps_t.append(self.update_t2(self.dict_R_ijab[iroot]))

            if (eps_t[iroot] <= self.conv): 
              self.count[iroot] = 1

            print ("             ------------------------")
            if (cc.rank_So > 1):
              print 'EPS for IROOT :',iroot+1, '  IS: ', eps_t[iroot], eps_So[iroot], eps_Sv[iroot]
            else:
              print 'EPS for IROOT :',iroot+1, '  IS: ', eps_t[iroot]
            print 'Eigenvalue for IROOT :',iroot+1, '  IS:  ', self.w[iroot], ' a.u. ', self.w[iroot]*27.2113839, ' eV'
            print ("             ------------------------")

          if (sum(self.count)== nroot):
            for iroot in range(0,nroot):
              print "!!!!!!!!!!CONVERGED!!!!!!!!!!!!"
              print 'Excitation Energy for sym', self.isym, 'iroot', iroot+1, ' :', self.w[iroot], ' a.u. ', self.w[iroot]*27.2113839, ' eV'
            tConverged = True
          else:
            tConverged = False
           
	  return tConverged

	def update_amplitudes(self, cc, data):

	  nroot = self.nroot

	  self.dict_new_r_t2 = {}
	  if (cc.rank_t1 > 0):
	    self.dict_new_r_t1 = {}

	  for iroot in range(0, nroot):
            self.dict_new_r_t2[iroot] = np.divide(self.dict_R_ijab[iroot],(data.D2 - self.w[iroot]))
	    if (cc.rank_t1 > 0):
              self.dict_new_r_t1[iroot] = np.divide(self.dict_R_ia[iroot],(data.D1 - self.w[iroot]))

          self.dict_R_ia = None
          self.dict_R_ijab = None

	def orthonormalize_amplitudes(self, cc, data):

	  nroot = self.nroot
	  r = self.r

	  dict_orth_r_t2 = self.dict_new_r_t2
          dict_norm_r_t2 = {}

	  if (cc.rank_t1 > 0):
	    dict_orth_r_t1 = self.dict_new_r_t1
            dict_norm_r_t1 = {}

	  for iroot in range(0, nroot):
	    for m in range(0,r+1):
	      for jroot in range(0, nroot):
	        if (cc.rank_t1 >  0):

                  ovrlap = self.calc_overlap(self.dict_new_r_t2[iroot],data.dict_r_t2[m,jroot], self.dict_new_r_t1[iroot],data.dict_r_t1[m,jroot])

                  dict_orth_r_t2[iroot] += -ovrlap*data.dict_r_t2[m, jroot]
                  dict_orth_r_t1[iroot] += -ovrlap*data.dict_r_t1[m, jroot]

		else: 

                  ovrlap = self.calc_overlap(self.dict_new_r_t2[iroot],data.dict_r_t2[m,jroot])

                  dict_orth_r_t2[iroot] += -ovrlap*data.dict_r_t2[m, jroot]

	    for jroot in range(0, iroot):

	        if (cc.rank_t1 >  0):

                  ovrlap = self.calc_overlap(dict_norm_r_t2[jroot], self.dict_new_r_t2[iroot], dict_norm_r_t1[jroot], self.dict_new_r_t1[iroot])

                  dict_orth_r_t2[iroot] += -ovrlap*dict_norm_r_t2[jroot]
                  dict_orth_r_t1[iroot] += -ovrlap*dict_norm_r_t1[jroot]

		else: 

                  ovrlap = self.calc_overlap(dict_orth_r_t2[jroot], self.dict_new_r_t2[iroot])

                  dict_orth_r_t2[iroot] += -ovrlap*dict_orth_r_t2[jroot]
	
	    if (cc.rank_t1 >  0):
	      # The ordering of the arguments is important here
	      dict_norm_r_t2[iroot], dict_norm_r_t1[iroot] = self.normalise_vector(dict_orth_r_t2[iroot], dict_orth_r_t1[iroot])
	    else:
	      dict_norm_r_t2[iroot] = self.normalise_vector(dict_orth_r_t2[iroot])

            data.dict_r_t2[r+1,iroot] = dict_norm_r_t2[iroot]
	    if (cc.rank_t1 >  0):
              data.dict_r_t1[r+1,iroot] = dict_norm_r_t1[iroot]

           #print 'Final norm: ', self.find_norm(dict_norm_r_t2[iroot], dict_norm_r_t1[iroot] )

        def calc_overlap(self, t2_a, t2_b, t1_a=None, t1_b=None, So_a=None, So_b=None, Sv_a=None, Sv_b=None):

          overlap = 2.0*np.einsum('ijab,ijab',t2_a, t2_b) - np.einsum('ijab,ijba',t2_a, t2_b)

          try:
            overlap += 2.0*np.einsum('ia,ia',t1_a, t1_b)
            try:
              overlap += 2.0*np.einsum('ijav,ijav',So_a,So_b) - np.einsum('ijav,jiav',So_a,So_b)
              overlap += 2.0*np.einsum('iuab,iuab',Sv_a,Sv_b) - np.einsum('iuab,iuba',Sv_a,Sv_b)
              return overlap
	    except: 
              return overlap
	  except:
            return overlap

          self.dict_new_r_t1 = None
          self.dict_new_r_t2 = None

        def use_overlap(self, overlap, t2, t1=None, So=None, Sv=None):

          t2 -= overlap*t2
	  try:
            t1 -= overlap*t1
	    try:
              So -= overlap*So
              Sv -= overlap*So
              return  t2, t1
	    except:
              return  t2, t1
	  except:
            return t2

        def iter_davidson(self, cc, data):

	  self.reshape_BMat(cc, data)
	  BMat = self.form_BMat(cc,data)

          w_total, vects_total = scipy.linalg.eig(BMat)
          
          if (np.all(w_total).imag <= 1e-8):
            w_total = w_total.real    

	  self.w, self.dict_coeff_total = self.select_vectors(w_total, vects_total)

	  self.expand_vector(cc, data)

	  self.calc_residue(cc, data)

          self.tConverged = self.check_convergence(cc, data)

          if ( not self.tConverged):
            self.update_amplitudes(cc, data)
    	    self.orthonormalize_amplitudes(cc, data)

        def reset_data(self, cc, data):

         nroot = self.nroot
         r = self.r

         data.dict_Y_ijab.clear()
         data.dict_r_t2.clear()
         data.B_Y_ijab = np.zeros((nroot*(r+1),nroot*(r+1)))
         for iroot in range(0,nroot):
           data.dict_r_t2[r, iroot] = self.dict_x_t2[iroot]
           print data.dict_r_t2[r, iroot]

         if (cc.rank_t1 > 0):
           data.dict_Y_ia.clear()
           data.dict_r_t1.clear()
           data.B_Y_ia = np.zeros((nroot*(r+1),nroot*(r+1)))
          
           for iroot in range(0,self.nroot):
             data.dict_r_t1[r, iroot] = self.dict_x_t1[iroot]
             print data.dict_r_t1[r, iroot]

	def exc_energy_sym(self, ind):

            self.init_all_data(self.cc_main, self.cc_main.AllData, ind)

	    self.print_statements(1, ind)
            for x in range(0, self.cc_main.maxiter):
                self.x = x
		self.r = x%self.nDavidson
		self.nroot = self.root_info[ind]
	        self.print_statements(2, ind)
                self.isym = ind

                if (x>0 and self.r==0):
                  self.reset_data(self.cc_main, self.cc_main.AllData)

		for iroot in range(0,self.root_info[ind]):
		    self.iroot = iroot
            	    self.calc_matrix_products(self.cc_main, self.cc_main.AllData)

		self.iter_davidson(self.cc_main, self.cc_main.AllData)

                if self.tConverged:
                  break

	def run(self):
	    for i, nroot in enumerate(self.root_info):
		if (nroot > 0):
		    self.exc_energy_sym(i)
		print 'Done calculation for ', i

        def print_statements(self, ind, isym):

	    if (ind == 1):

##-----------------------------------------------------------------##
                      #Iteration begins#

##-----------------------------------------------------------------##
                print ("---------------------------------------------------------")
                print ("               Molecular point group   "+str(isym))
                print ("    Linear Response iteration begins for symmetry   "+str(isym))
                print ("---------------------------------------------------------")

	    elif (ind == 2): 

                print ("")
                print ("-------------------------------------------------")
                print ("          Iteration number "+str(self.x))
                print ("          Subspace vector "+str(self.r))
                print ("-------------------------------------------------")
  
if __name__ == '__main__':

    mol = pyscf.gto.M(
    verbose = 5,
    output = None,
    unit='Bohr',
    atom ='''
    Li  0.000000,  0.000000, -0.3797714041
    H   0.000000,  0.000000,  2.6437904102
    ''',
    basis = 'sto-3g',
    symmetry = 'C2v',
    )

    mf = scf.RHF(mol).run()
    cc_res = state(mf)
    cc_res.variant = 'CCSD'
    if (cc_res.variant == 'ICCSD'):
        cc_res.no_act = 1
        cc_res.nv_act = 1
    cc_res.max_diis = 7
    cc_res.maxiter = 50
    cc_res.energy.run()

    cc_res.exc_en.root_info = [2,0,0,0]
    cc_res.maxiter = 2
    cc_res.exc_en.conv = 1e-6
    cc_res.exc_en.nDavidson = 5
    cc_res.exc_en.run()
