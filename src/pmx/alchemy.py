#!/usr/bin/env python

"""This module contains functions that can be used to setup the hybrid
structures and topologies needed for alchemical free energy calculations.
"""

from __future__ import absolute_import, print_function, division
from builtins import map
import os
import sys
from copy import deepcopy
from . import library
from .model import Model
from .utils import mtpError, UnknownResidueError, MissingTopolParamError
from .geometry import Rotation, nuc_super, bb_super
from .mutdb import read_mtp_entry
from .forcefield import Topology, _check_case, _atoms_morphe
from .utils import get_mtp_file

__all__ = ['mutate', 'gen_hybrid_top', 'write_split_top']


# ==============
# Main Functions
# ==============
def mutate(m, mut_resid, mut_resname, ff, mut_chain=None,
           refB=None, inplace=False, verbose=False):
    """Creates an hybrid structure file.

    Parameters
    ----------
    m : Model
        the model to be mutated. See :py:class:`pmx.model.Model`.
    mut_resid : int
        the ID of the residue to be mutated.
    mut_resname : str
        the name of the target residue.
    ff : str
        the forcefield to use.
    mut_chain : str, optional
        the chain ID for the residue you want to mutate. This is needed if you
        have multiple chains and are providing a Model that did not have its
        residues renumbered.
    refB : str, optional
        reference structure file of the B state in PDB or GRO format. If it is
        provided, the dummy atoms will be built based on the position of the
        atoms in this structure. This option is available only for Protein
        mutations.
    inplace : bool, optional
        whether to modify the input Model in place. Default is False.
    verbose : bool, optional
        whether to print info. Default is False.

    Returns
    -------
    m2 : Model
        model with mutated residues. If argument 'inplace' is True, nothing is
        returned.
    """

    if inplace is True:
        m2 = m
    elif inplace is False:
        m2 = deepcopy(m)

    # convert Model to Angstrom units: this code works on A units
    if m2.unity == 'nm':
        m2.nm2a()
        if verbose:
            print('Model units have been converted from nm to A.')

    # get the residue based on the index
    # fetch_residue also checks the selection is valid and unique
    residue = m2.fetch_residue(idx=mut_resid, chain=mut_chain)
    # get the correct mtp file
    mtp_file = get_mtp_file(residue, ff)

    # Mutation if Protein
    if residue.moltype == 'protein':
        new_aa_name = _convert_aa_name(mut_resname)
        apply_aa_mutation(m=m2, residue=residue, new_aa_name=new_aa_name,
                          mtp_file=mtp_file, refB=refB, verbose=verbose)
    # Mutation if DNA or RNA
    elif residue.moltype in ['dna', 'rna']:
        new_nuc_name = mut_resname.upper()
        apply_nuc_mutation(m=m2, residue=residue, new_nuc_name=new_nuc_name,
                           mtp_file=mtp_file, verbose=verbose)

    if inplace is False:
        return m2


def apply_aa_mutation(m, residue, new_aa_name, mtp_file, refB=None,
                      verbose=False):

    if residue.resname == 'ILE':
        _rename_ile(residue)
    olkey = _convert_aa_name(residue.resname)

    # olkey should contain the correct one letter name of the WT residue
    # however, due to the different namings of the residues in the FFs
    # Lys needs to be checked once again: in OPLS Lys is non-protonated,
    # while in the other FFs it is protonated
    if ('opls' in mtp_file) and ('LYS' in residue.resname):
        olkey = _check_OPLS_LYS(residue)

    hybrid_residue_name = olkey+'2'+new_aa_name
    if verbose is True:
        print('log_> Residue to mutate: %d | %s | %s ' % (residue.id, residue.resname, residue.chain_id))
        print('log_> Mutation to apply: %s->%s' % (olkey, new_aa_name))
        print('log_> Hybrid residue name: %s' % hybrid_residue_name)
    hybrid_res, bonds, imps, diheds, rotdic = _get_hybrid_residue(residue_name=hybrid_residue_name,
                                                                  mtp_file=mtp_file,
                                                                  version='new',
                                                                  verbose=False)
    bb_super(residue, hybrid_res)

    # rename residue atoms
    hash1 = _rename_to_match_library(residue)
    hash2 = _rename_to_match_library(hybrid_res)
    _set_conformation(residue, hybrid_res, rotdic)
    if refB is not None:
        if verbose is True:
            print("log_> Set Bstate geometry according to the provided structure")
        mB = Model(refB, bPDBTER=True, rename_atoms=True, scale_coords='A')
        residueB = mB.residues[residue.id-1]
        bb_super(residue, residueB)
        for atom in hybrid_res.atoms:
            if (atom.name[0] == 'D') or atom.name.startswith('HV'):
                for atomB in residueB.atoms:
                    if atomB.name == hybrid_res.morphes[atom.name]['n1']:
                        atom.x = atomB.x
    _rename_back(residue, hash1)
    _rename_back(hybrid_res, hash2)

    # do the actual replacement
    m.replace_residue(residue=residue, new=hybrid_res, bKeepResNum=True)

    if verbose is True:
        print('log_> Inserted hybrid residue %s at position %d (chain %s)' %
              (hybrid_res.resname, hybrid_res.id, hybrid_res.chain_id))


def apply_nuc_mutation(m, residue, new_nuc_name, mtp_file, verbose=False):

    hybrid_residue_name, resname1, resname2 = get_nuc_hybrid_resname(residue, new_nuc_name)
    if verbose is True:
        print('log_> Residue to mutate: %d | %s | %s ' % (residue.id, residue.resname, residue.chain_id))
        print('log_> Mutation to apply: %s->%s' % (residue.resname[1], new_nuc_name))
        print('log_> Hybrid residue name: %s' % hybrid_residue_name)
    hybrid_res, bonds, imps, diheds, rotdic = _get_hybrid_residue(residue_name=hybrid_residue_name,
                                                                  mtp_file=mtp_file,
                                                                  version='new',
                                                                  verbose=False)

    nuc_super(residue, hybrid_res, resname1, resname2)
    for atom in hybrid_res.atoms:
        if atom.name[0] != 'D':
            atom.x = residue[atom.name].x
    m.replace_residue(residue=residue, new=hybrid_res, bKeepResNum=True)
    if verbose is True:
        print('log_> Inserted hybrid residue %s at position %d (chain %s)' %
              (hybrid_res.resname, hybrid_res.id, hybrid_res.chain_id))


def get_nuc_hybrid_resname(residue, new_nuc_name):

    if residue.moltype == 'dna':
        firstLetter = 'D'
    if residue.moltype == 'rna':
        firstLetter = 'R'

    # identify if the nucleotide is terminal
    for a in residue.atoms:
        if a.name == 'H3T':
            r1 = firstLetter+residue.resname[1]+'3'
            r2 = firstLetter+new_nuc_name+'3'
            dict_key = r1+'_'+r2
            if residue.moltype == 'rna':
                hybrid_residue_name = _rna_names[dict_key]
            else:
                hybrid_residue_name = _dna_names[dict_key]
            return(hybrid_residue_name, residue.resname[1], new_nuc_name)
        elif a.name == 'H5T':
            r1 = firstLetter+residue.resname[1]+'5'
            r2 = firstLetter+new_nuc_name+'5'
            dict_key = r1+'_'+r2
            if residue.moltype == 'rna':
                hybrid_residue_name = _rna_names[dict_key]
            else:
                hybrid_residue_name = _dna_names[dict_key]
            return(hybrid_residue_name, residue.resname[1], new_nuc_name)
    hybrid_residue_name = residue.resname+new_nuc_name
    return(hybrid_residue_name, residue.resname[1], new_nuc_name)


def gen_hybrid_top(topol, recursive=True, verbose=False):
    """Fills the bstate of a topology file containing pmx hybrid residues. This
    can be either a top or itp file. If the file contains other itp files via
    include statements, the function can iterate through them if the recursive
    flag is set to True.

    It returns a Topology instance with b states filled for the input topol
    instance, and optionally a list of additional Topology instances for the
    included itp files. If there are no itp files, or if recursive is set to
    False, then an empty list is returned.

    Parameters
    ----------
    topol : Topology
        input Topology instance
    recursive : bool, optional
        whether to fill b states also for all itp files included in the
        topology file. Default is True.
    verbose : bool
        whether to print out info. Default is False.

    Returns
    -------
    top, itps : obj, list of obj
        output Topology instance with b states assigned (top), and
        list of Topology instances for the additional itp files (itps)
        included in the input topology.
    """

    # ff setup
    ff = topol.forcefield
    ffbonded_file = os.path.join(topol.ffpath, 'ffbonded.itp')

    # main function that returns the Topology with filled B states
    def process_topol(topol, ff, ffbonded_file, verbose=False):
        pmxtop = deepcopy(topol)
        # create model with residue list
        m = Model(atoms=pmxtop.atoms)
        # use model residue list
        pmxtop.residues = m.residues
        # get list of hybrid residues and their params
        rlist, rdic = _get_hybrid_residues(m=m, ff=ff, version='new',
                                           verbose=verbose)
        # correct b-states
        pmxtop.assign_fftypes()
        if verbose is True:
            for r in rlist:
                print('log_> Hybrid Residue -> %d | %s ' % (r.id, r.resname))

        _find_bonded_entries(pmxtop, verbose=verbose)
        _find_angle_entries(pmxtop, verbose=verbose)
        dih_predef_default = []
        _find_predefined_dihedrals(pmxtop, rlist, rdic, ffbonded_file,
                                   dih_predef_default, ff)
        _find_dihedral_entries(pmxtop, rlist, rdic, dih_predef_default,
                               verbose=verbose)

        _add_extra_DNA_RNA_impropers(pmxtop, rlist, 1, [180, 40, 2], [180, 40, 2])

        if verbose is True:
            print('log_> Total charge of state A = %.f' % pmxtop.get_qA())
            print('log_> Total charge of state B = %.f' % pmxtop.get_qB())

        # if prolines are involved, break one bond (CD-CG)
        # and angles X-CD-CG, CD-CG-X
        # and dihedrals with CD and CG
        _proline_decouplings(pmxtop, rlist, rdic)
        # also decouple all dihedrals with [CD and N] and [CB and Calpha] for proline
        _proline_dihedral_decouplings(pmxtop, rlist, rdic)
        return pmxtop

    # -------------
    # Main topology
    # -------------
    if verbose is True:
        print('\nlog_> Reading input %s file "%s"'
              % (topol.filename.split('.')[-1], topol.filename))
    pmx_top = process_topol(topol=topol, ff=ff, ffbonded_file=ffbonded_file,
                            verbose=verbose)

    # ------------------------------------
    # itps too if asked for and if present
    # ------------------------------------
    itps = topol.include_itps
    pmx_itps = []
    if recursive is True and len(itps) > 0:
        for itp in itps:
            if verbose is True:
                print('\nlog_> Reading input itp file "%s""' % (itp))
            itp_path = os.path.dirname(os.path.relpath(topol.filename))
            itp_filename = os.path.join(itp_path, itp)
            topol2 = Topology(itp_filename, ff=ff, version='new')
            # fill b states
            pmx_itp = process_topol(topol=topol2, ff=ff,
                                    ffbonded_file=ffbonded_file,
                                    verbose=verbose)
            pmx_itps.append(pmx_itp)

    return pmx_top, pmx_itps


def write_split_top(pmxtop, outfile='pmxtop.top', scale_mass=False,
                    verbose=False):
    """
    Write three topology files to be used for three separate free energy
    calculations: charges off, vdw on, changes on. This can be useful when one
    wants to avoid using a soft-core for the electrostatic interactions.

    Parameters
    ----------
    pmxtop : Topology
        Topology object with B states defined.
    outfile : str
        name of output topology file.
    scale_mass : bool
        whether to scale the masses of morphing atoms
    verbose : bool
        whether to print information or not

    Returns
    -------
    None
    """

    root, ext = os.path.splitext(outfile)
    out_file_qoff = root + '_qoff' + ext
    out_file_vdw = root + '_vdw' + ext
    out_file_qon = root + '_qon' + ext

    # get charge of states A/B for hybrid residues
    qA = pmxtop.get_hybrid_qA()
    qB = pmxtop.get_hybrid_qB()

    if verbose is True:
        print('------------------------------------------------------')
        print('log_> Creating splitted topologies............')

        print('log_> Making "qoff" topology : "%s"' % out_file_qoff)
    contQ = deepcopy(qA)
    pmxtop.write(out_file_qoff, stateQ='AB', stateTypes='AA', dummy_qB='off',
                 scale_mass=scale_mass, target_qB=qA, stateBonded='AA',
                 full_morphe=False)
    if verbose is True:
        print('log_> Charge of state A: %g' % pmxtop.qA)
        print('log_> Charge of state B: %g' % pmxtop.qB)
    if verbose is True:
        print('------------------------------------------------------')
        print('log_> Making "vdw" topology : "%s"' % out_file_vdw)
    contQ = deepcopy(qA)
    pmxtop.write(out_file_vdw, stateQ='BB', stateTypes='AB', dummy_qA='off',
                 dummy_qB='off', scale_mass=scale_mass,
                 target_qB=contQ, stateBonded='AB', full_morphe=False)
    if verbose is True:
        print('log_> Charge of state A: %g' % pmxtop.qA)
        print('log_> Charge of state B: %g' % pmxtop.qB)
        print('------------------------------------------------------')

        print('log_> Making "qon" topology : "%s"' % out_file_qon)
    pmxtop.write(out_file_qon, stateQ='BB', stateTypes='BB', dummy_qA='off',
                 dummy_qB='on', scale_mass=scale_mass, target_qB=qB,
                 stateBonded='BB', full_morphe=False)
    if verbose is True:
        print('log_> Charge of state A: %g' % pmxtop.qA)
        print('log_> Charge of state B: %g' % pmxtop.qB)
        print('------------------------------------------------------')


# ===============
# HelperFunctions
# ===============
def _check_OPLS_LYS(res):
    if res.has_atom('HZ3'):
        return('K')
    else:
        return('O')


def _convert_aa_name(aa):
    # firstly, some special deprotonated cases
    if aa == 'CM':
        return(aa.upper())
    elif len(aa) == 1:
        return aa.upper()
    elif len(aa) in [3, 4]:
        return library._ext_one_letter[aa.upper()]
    else:
        raise UnknownResidueError(aa)


def _rename_ile(residue):
    dic = {'CD':  'CD1',
           'HD1': 'HD11',
           'HD2': 'HD12',
           'HD3': 'HD13'
           }
    for key, value in dic.items():
        try:
            atom = residue[key]
            atom.name = value
        except:
            pass


def _rename_to_match_library(res):
    name_hash = {}
    atoms = res.atoms
    for atom in atoms:
        foo = atom.name
        # for serine
        if (atom.resname == 'SER') and (atom.name == 'HG1'):
            atom.name = 'HG'
        if ('S2' in atom.resname) and (atom.name == 'HG1'):
            atom.name = 'HG'
        # for cysteine
        if (atom.resname == 'CYS') and (atom.name == 'HG1'):
            atom.name = 'HG'
        if ('C2' in atom.resname) and (atom.name == 'HG1'):
            atom.name = 'HG'

        name_hash[atom.name] = foo
    return name_hash


def _rename_back(res, name_hash):
    for atom in res.atoms:
        atom.name = name_hash[atom.name]


def _set_conformation(old_res, new_res, rotdic):
    old_res.get_real_resname()
    dihedrals = library._aa_dihedrals[old_res.real_resname]
    for key, lst in rotdic.items():
        new = new_res.fetchm(lst)
        rotdic[key] = new
    chis = []
    for key in rotdic.keys():
        at1, at2 = key.split('-')
        for d in dihedrals:
            if d[1] == at1 and d[2] == at2 \
                   and d[-1] != -1:
                chis.append(d)
    for d in chis:
        atoms = old_res.fetchm(d[:4])
        phi = atoms[0].dihedral(atoms[1], atoms[2], atoms[3])
        atoms2 = new_res.fetchm(d[:4])
        phi2 = atoms2[0].dihedral(atoms2[1], atoms2[2], atoms2[3])
        diff = phi-phi2
        a1, a2 = new_res.fetchm(d[1:3])
        key = a1.name+'-'+a2.name
        atoms = rotdic[key]
        rot = Rotation(a1.x, a2.x)
        for atom in atoms:
            atom.x = rot.apply(atom.x, diff)
    for atom in new_res.atoms:
        if (atom.name[0] != 'D') and (not atom.name.startswith('HV')):
            atom.x = old_res[atom.name].x


def _proline_dihedral_decouplings(topol, rlist, rdic):
    for r in rlist:
        if 'P' in r.resname:
            # identify in which state proline sits
            prolineState = 'A'
            if '2P' in r.resname:
                prolineState = 'B'

            # find the atoms for which the bond needs to be broken
            prolineCDatom = ''
            prolineCBatom = ''
            prolineNatom = ''
            prolineCAatom = ''
            for a in r.atoms:
                if (prolineState == 'A') and (a.name == 'CD'):
                    prolineCDatom = a
                elif (prolineState == 'A') and (a.name == 'N'):
                    prolineNatom = a
                elif (prolineState == 'A') and (a.name == 'CB'):
                    prolineCBatom = a
                elif (prolineState == 'A') and (a.name == 'CA'):
                    prolineCAatom = a
                elif (prolineState == 'B') and (a.name == 'DCD'):
                    prolineCDatom = a
                elif (prolineState == 'B') and (a.name == 'N'):
                    prolineNatom = a
                elif (prolineState == 'B') and (a.name == 'DCB'):
                    prolineCBatom = a
                elif (prolineState == 'B') and (a.name == 'CA'):
                    prolineCAatom = a

            # decouple [CD and N] dihedrals
            for dih in topol.dihedrals:
                a1 = dih[0]
                a2 = dih[1]
                a3 = dih[2]
                a4 = dih[3]
                func = dih[4]
                if ((a1.id == prolineCDatom.id and a2.id == prolineNatom.id)) or \
                   ((a2.id == prolineCDatom.id and a1.id == prolineNatom.id)) or \
                   ((a1.id == prolineCDatom.id and a3.id == prolineNatom.id)) or \
                   ((a3.id == prolineCDatom.id and a1.id == prolineNatom.id)) or \
                   ((a1.id == prolineCDatom.id and a4.id == prolineNatom.id)) or \
                   ((a4.id == prolineCDatom.id and a1.id == prolineNatom.id)) or \
                   ((a2.id == prolineCDatom.id and a3.id == prolineNatom.id)) or \
                   ((a3.id == prolineCDatom.id and a2.id == prolineNatom.id)) or \
                   ((a2.id == prolineCDatom.id and a4.id == prolineNatom.id)) or \
                   ((a4.id == prolineCDatom.id and a2.id == prolineNatom.id)) or \
                   ((a3.id == prolineCDatom.id and a4.id == prolineNatom.id)) or \
                   ((a4.id == prolineCDatom.id and a3.id == prolineNatom.id)):
                    if (dih[5] == 'NULL') or (dih[6] == 'NULL'):
                        continue
                    if prolineState == 'A':
                        if func == 3:
                            dih[6] = [func, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        elif func == 2:
                            dih[6] = [func, dih[6][1], 0.0]
                        else:
                            dih[6] = [func, dih[6][1], 0.0, dih[6][-1]]
                    if prolineState == 'B':
                        if func == 3:
                            dih[5] = [func, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        elif func == 2:
                            dih[5] = [func, dih[6][1], 0.0]
                        else:
                            dih[5] = [func, dih[6][1], 0.0, dih[6][-1]]

            # decouple [CB and CA] dihedrals
            for dih in topol.dihedrals:
                a1 = dih[0]
                a2 = dih[1]
                a3 = dih[2]
                a4 = dih[3]
                func = dih[4]
                if ((a1.id == prolineCBatom.id and a2.id == prolineCAatom.id)) or \
                   ((a2.id == prolineCBatom.id and a1.id == prolineCAatom.id)) or \
                   ((a1.id == prolineCBatom.id and a3.id == prolineCAatom.id)) or \
                   ((a3.id == prolineCBatom.id and a1.id == prolineCAatom.id)) or \
                   ((a1.id == prolineCBatom.id and a4.id == prolineCAatom.id)) or \
                   ((a4.id == prolineCBatom.id and a1.id == prolineCAatom.id)) or \
                   ((a2.id == prolineCBatom.id and a3.id == prolineCAatom.id)) or \
                   ((a3.id == prolineCBatom.id and a2.id == prolineCAatom.id)) or \
                   ((a2.id == prolineCBatom.id and a4.id == prolineCAatom.id)) or \
                   ((a4.id == prolineCBatom.id and a2.id == prolineCAatom.id)) or \
                   ((a3.id == prolineCBatom.id and a4.id == prolineCAatom.id)) or \
                   ((a4.id == prolineCBatom.id and a3.id == prolineCAatom.id)):
                    if (dih[5] == 'NULL') or (dih[6] == 'NULL'):
                        continue
                    if prolineState == 'A':
                        if func == 3:
                            dih[6] = [func, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        elif func == 2:
                            dih[6] = [func, dih[6][1], 0.0]
                        else:
                            dih[6] = [func, dih[6][1], 0.0, dih[6][-1]]
                    if prolineState == 'B':
                        if func == 3:
                            dih[5] = [func, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        elif func == 2:
                            dih[5] = [func, dih[6][1], 0.0]
                        else:
                            dih[5] = [func, dih[6][1], 0.0, dih[6][-1]]


def _proline_decouplings(topol, rlist, rdic):
    for r in rlist:
        if 'P' in r.resname:
            # identify in which state proline sits
            prolineState = 'A'
            if '2P' in r.resname:
                prolineState = 'B'

            # find the atoms for which the bond needs to be broken
            prolineCDatom = ''
            prolineCGatom = ''
            for a in r.atoms:
                if (prolineState == 'A') and (a.name == 'CD'):
                    prolineCDatom = a
                elif (prolineState == 'A') and (a.name == 'CG'):
                    prolineCGatom = a
                elif (prolineState == 'B') and (a.name == 'DCD'):
                    prolineCDatom = a
                elif (prolineState == 'B') and (a.name == 'DCG'):
                    prolineCGatom = a

            # break the bond
            for b in topol.bonds:
                a1 = b[0]
                a2 = b[1]
                if ((a1.id == prolineCDatom.id) and (a2.id == prolineCGatom.id)) or \
                   ((a2.id == prolineCDatom.id) and (a1.id == prolineCGatom.id)):
                    if prolineState == 'A':
                        b[4] = deepcopy(b[3])
                        b[4][2] = 0.0
                    elif prolineState == 'B':
                        b[3] = deepcopy(b[4])
                        b[3][2] = 0.0

            # decouple angles
            for ang in topol.angles:
                a1 = ang[0]
                a2 = ang[1]
                a3 = ang[2]
                func = ang[3]
                if ((a1.id == prolineCDatom.id and a2.id == prolineCGatom.id)) or \
                   ((a2.id == prolineCDatom.id and a1.id == prolineCGatom.id)) or \
                   ((a1.id == prolineCDatom.id and a3.id == prolineCGatom.id)) or \
                   ((a3.id == prolineCDatom.id and a1.id == prolineCGatom.id)) or \
                   ((a2.id == prolineCDatom.id and a3.id == prolineCGatom.id)) or \
                   ((a3.id == prolineCDatom.id and a2.id == prolineCGatom.id)):
                    if prolineState == 'A':
                        if func == 5:
                            ang[5] = [1, 0, 0, 0, 0]
                        else:
                            ang[5] = [1, 0, 0]
                    elif prolineState == 'B':
                        if func == 5:
                            ang[4] = [1, 0, 0, 0, 0]
                        else:
                            ang[4] = [1, 0, 0]

            # decouple dihedrals
            for dih in topol.dihedrals:
                a1 = dih[0]
                a2 = dih[1]
                a3 = dih[2]
                a4 = dih[3]
                func = dih[4]
                if ((a1.id == prolineCDatom.id and a2.id == prolineCGatom.id)) or \
                   ((a2.id == prolineCDatom.id and a1.id == prolineCGatom.id)) or \
                   ((a1.id == prolineCDatom.id and a3.id == prolineCGatom.id)) or \
                   ((a3.id == prolineCDatom.id and a1.id == prolineCGatom.id)) or \
                   ((a1.id == prolineCDatom.id and a4.id == prolineCGatom.id)) or \
                   ((a4.id == prolineCDatom.id and a1.id == prolineCGatom.id)) or \
                   ((a2.id == prolineCDatom.id and a3.id == prolineCGatom.id)) or \
                   ((a3.id == prolineCDatom.id and a2.id == prolineCGatom.id)) or \
                   ((a2.id == prolineCDatom.id and a4.id == prolineCGatom.id)) or \
                   ((a4.id == prolineCDatom.id and a2.id == prolineCGatom.id)) or \
                   ((a3.id == prolineCDatom.id and a4.id == prolineCGatom.id)) or \
                   ((a4.id == prolineCDatom.id and a3.id == prolineCGatom.id)):
                    if (dih[5] == 'NULL') or (dih[6] == 'NULL'):
                        continue

                    if prolineState == 'A':
                        if func == 3:
                            dih[6] = [func, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        elif func == 2:
                            dih[6] = [func, dih[6][1], 0.0]
                        else:
                            dih[6] = [func, dih[6][1], 0.0, dih[6][-1]]
                    if prolineState == 'B':
                        if func == 3:
                            dih[5] = [func, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                        elif func == 2:
                            dih[5] = [func, dih[6][1], 0.0]
                        else:
                            dih[5] = [func, dih[6][1], 0.0, dih[6][-1]]


def _find_bonded_entries(topol, verbose=False):
    count = 0
    for b in topol.bonds:
        a1, a2, func = b
        A, B = _check_case([a1, a2])
        if a1.atomtypeB is not None or a2.atomtypeB is not None:
            count += 1
            error_occured = False
            astate = None
            bstate = None
            if A == 'AA' and B == 'AA':  # we need A and B state
                astate = topol.BondedParams.get_bond_param(a1.type, a2.type)
                bstate = topol.BondedParams.get_bond_param(a1.typeB, a2.typeB)
                b.extend([astate, bstate])
            elif 'D' in A and B == 'AA':
                bstate = topol.BondedParams.get_bond_param(a1.typeB, a2.typeB)
                astate = bstate
                b.extend([astate, bstate])
            elif 'D' in B and A == 'AA':
                astate = topol.BondedParams.get_bond_param(a1.type, a2.type)
                bstate = astate
                b.extend([astate, bstate])
            # catch errors
            elif 'D' in B and 'D' in A:
                print('Error: fake bond '
                      '%s-%s (%s-%s -> %s-%s)' % (a1.name, a2.name,
                                                  a1.atomtype, a2.atomtype,
                                                  a1.atomtypeB, a2.atomtypeB))
                sys.exit(1)
            if astate is None:
                print('Error A: No bond entry found for astate '
                      '%s-%s (%s-%s -> %s-%s)' % (a1.name, a2.name,
                                                  a1.atomtype, a2.atomtype,
                                                  a1.type, a2.type))
                print('Resi = %s' % a1.resname)
                error_occured = True

            if bstate is None:
                print('Error B: No bond entry found for bstate '
                      '%s-%s (%s-%s -> %s-%s)' % (a1.name, a2.name,
                                                  a1.atomtypeB, a2.atomtypeB,
                                                  a1.typeB, a2.typeB))
                error_occured = True
            if error_occured:
                sys.exit(1)
    if verbose is True:
        print('log_> Making bonds for state B -> %d bonds with perturbed atoms'
              % count)


def _find_angle_entries(topol, verbose=False):
    count = 0
    for a in topol.angles:
        a1, a2, a3, func = a
        astate = None
        bstate = None
        if a1.atomtypeB is not None or \
           a2.atomtypeB is not None or \
           a3.atomtypeB is not None:
            A, B = _check_case([a1, a2, a3])
            count += 1
            if 'D' in A and 'D' in B:  # fake angle
                if func == 5:
                    astate = [1, 0, 0, 0, 0]
                    bstate = [1, 0, 0, 0, 0]
                else:
                    astate = [1, 0, 0]
                    bstate = [1, 0, 0]
                a.extend([astate, bstate])
            elif A == 'AAA' and 'D' in B:   # take astate
                astate = topol.BondedParams.get_angle_param(a1.type,
                                                            a2.type,
                                                            a3.type)
                bstate = astate
                a.extend([astate, bstate])
            elif 'D' in A and B == 'AAA':   # take bstate
                bstate = topol.BondedParams.get_angle_param(a1.typeB,
                                                            a2.typeB,
                                                            a3.typeB)
                astate = bstate
                a.extend([astate, bstate])
            elif A == 'AAA' and B == 'AAA':
                if a1.atomtypeB != a1.atomtype or \
                   a2.atomtypeB != a2.atomtype or \
                   a3.atomtypeB != a3.atomtype:
                    astate = topol.BondedParams.get_angle_param(a1.type,
                                                                a2.type,
                                                                a3.type)
                    bstate = topol.BondedParams.get_angle_param(a1.typeB,
                                                                a2.typeB,
                                                                a3.typeB)
                    a.extend([astate, bstate])
                else:
                    astate = topol.BondedParams.get_angle_param(a1.type,
                                                                a2.type,
                                                                a3.type)
                    bstate = astate
                    a.extend([astate, bstate])
            if astate is None:
                raise MissingTopolParamError("No angle entry (state A)",
                                             [a1, a2, a3])
            if bstate is None:
                raise MissingTopolParamError("No angle entry (state B)",
                                             [a1, a2, a3])

    if verbose is True:
        print('log_> Making angles for state B -> %d angles with perturbed atoms'
              % count)


def _find_dihedral_entries(topol, rlist, rdic, dih_predef_default,
                           verbose=False):
    count = 0
    nfake = 0
    # here I will accumulate multiple entries of type 9 dihedrals
    dih9 = []
    # need to store already visited angles to avoid multiple re-definitions
    visited_dih = []

    for d in topol.dihedrals:
        if len(d) >= 6:
            # only consider the dihedral, if it has not been encountered so far
            undef = 0
            encountered = 0

            undef, encountered = _is_dih_undef(dih_predef_default, d)
            encountered = _is_dih_encountered_strict(visited_dih, d,
                                                     encountered)
            if(encountered == 1):
                continue

            visited_dih.append(d)

            if undef == 3 or undef == 4:
                a1 = d[0]
                a2 = d[1]
                a3 = d[2]
                a4 = d[3]
                val = ''
                func = 9
            elif(len(d) == 6):
                a1, a2, a3, a4, func, val = d
            else:
                a1, a2, a3, a4, func, val, rest = d

            backup_d = d[:6]

            if _atoms_morphe([a1, a2, a3, a4]):
                A, B = _check_case(d[:4])
                if A != 'AAAA' and B != 'AAAA':
                    nfake += 1
                    # these are fake dihedrals
                    d[5] = 'NULL'
                    d.append('NULL')
                else:
                    count += 1
                    astate = []
                    bstate = []
                    if A == 'AAAA' and B != 'AAAA':
                        foo = topol.BondedParams.get_dihedral_param(a1.type,
                                                                    a2.type,
                                                                    a3.type,
                                                                    a4.type,
                                                                    func)
                        # need to check if the dihedral has torsion pre-defined
                        counter = _check_dih_ILDN_OPLS(topol, rlist, rdic,
                                                       a1, a2, a3, a4)
                        if counter == 42:
                            continue

                        for ast in foo:
                            if counter == 0:
                                d[5] = ast
                                d.append(ast)
                            else:
                                alus = backup_d[:]
                                alus[5] = ast
                                alus.append(ast)
                                dih9.append(alus)
                            counter = 1

                    elif B == 'AAAA' and A != 'AAAA':
                        foo = topol.BondedParams.get_dihedral_param(a1.typeB,
                                                                    a2.typeB,
                                                                    a3.typeB,
                                                                    a4.typeB,
                                                                    func)
                        # need to check if the dihedral has torsion pre-defined
                        counter = _check_dih_ILDN_OPLS(topol, rlist, rdic, a1, a2, a3, a4)

                        if counter == 42:
                            continue

                        for bst in foo:
                            if counter == 0:
                                d[5] = bst
                                d.append(bst)
                            else:
                                alus = backup_d[:]
                                alus[5] = bst
                                alus.append(bst)
                                dih9.append(alus)
                            counter = 1

                    elif A == 'AAAA' and B == 'AAAA':
                        # disappear/appear dihedrals, do not morphe
                        if val == '':
                            if(undef != 4):
                                astate = topol.BondedParams.get_dihedral_param(a1.type,
                                                                               a2.type,
                                                                               a3.type,
                                                                               a4.type,
                                                                               func)
                        else:
                            if(undef != 4):
                                astate = topol.BondedParams.get_dihedral_param(a1.type,
                                                                               a2.type,
                                                                               a3.type,
                                                                               a4.type,
                                                                               func)
                        # if types_morphe([a1,a2,a3,a4]):
                        if (undef != 3):
                                bstate = topol.BondedParams.get_dihedral_param(a1.typeB,
                                                                               a2.typeB,
                                                                               a3.typeB,
                                                                               a4.typeB,
                                                                               func)

                        if undef == 1 and astate == []:
                            continue
                        elif undef == 1 and (astate[0][0] == 4 or astate[0][0] == 2):
                            continue
                        elif undef == 2 and bstate == []:
                            continue
                        elif undef == 2 and (bstate[0][0] == 4 or bstate[0][0] == 2):
                            continue

                        # need to check if the dihedral has torsion pre-defined
                        counter = _check_dih_ILDN_OPLS(topol, rlist, rdic,
                                                       a1, a2, a3, a4)

                        # torsion for both states defined, change nothing
                        if counter == 42:
                            continue

                        # A state disappears (when going to B)
                        for ast in astate:
                            if counter == 0:
                                d[5] = ast
                                if ast[0] == 3:
                                    bst = [ast[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                                elif ast[0] == 2:
                                    bst = [ast[0], ast[1], 0.0]
                                else:
                                    bst = [ast[0], ast[1], 0.0, ast[-1]]
                                if len(d) == 6:
                                    d.append(bst)
                                else:
                                    d[6] = bst
                                counter = 1
                            elif counter == 1 or counter == 3:
                                alus = backup_d[:]
                                alus[5] = ast
                                if ast[0] == 3:
                                    bst = [ast[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                                elif ast[0] == 2:
                                    bst = [ast[0], ast[1], 0.0]
                                else:
                                    bst = [ast[0], ast[1], 0.0, ast[-1]]

                                alus.append(bst)
                                dih9.append(alus)

                        # B state disappears (when going to A)
                        # all must go to the new (appendable) dihedrals
                        for bst in bstate:
                            if counter == 0:
                                if bst[0] == 3:
                                    ast = [bst[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                                elif bst[0] == 2:
                                    ast = [bst[0], bst[1], 0.0]
                                else:
                                    ast = [bst[0], bst[1], 0.0, bst[-1]]
                                d[5] = ast
                                if len(d) == 6:
                                    d.append(bst)
                                else:
                                    d[6] = bst
                                counter = 1
                            elif counter == 1 or counter == 2:
                                alus = backup_d[:]
                                if ast[0] == 3:
                                    ast = [bst[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                                elif ast[0] == 2:
                                    ast = [bst[0], bst[1], 0.0]
                                else:
                                    ast = [bst[0], bst[1], 0.0, bst[-1]]
                                alus[5] = ast
                                alus.append(bst)
                                dih9.append(alus)


                    if astate is None:
                        print('Error: No dihedral angle found (state A: predefined state B) for:')
                        print('{0} {1} {2} {3}'.format(a1.resname, a2.resname, a3.resname, a4.resname))
                        print('{0} {1} {2} {3}'.format(a1.name, a2.name, a3.name, a4.name, func))
                        print('{0} {1} {2} {3}'.format(a1.atomtype, a2.atomtype, a3.atomtype, a4.atomtype))
                        print('{0} {1} {2} {3}'.format(a1.type, a2.type, a3.type, a4.type))
                        print('{0} {1} {2} {3}'.format(a1.atomtypeB, a2.atomtypeB, a3.atomtypeB, a4.atomtypeB))
                        print('{0} {1} {2} {3}'.format(a1.typeB, a2.typeB, a3.typeB, a4.typeB))
                        print('{0}'.format(astate))
                        print('{0}'.format(d))
                        sys.exit(1)

                    if bstate is None:
                        print('Error: No dihedral angle found (state B: predefined state A) for:')
                        print('{0} {1} {2} {3}'.format(a1.resname, a2.resname, a3.resname, a4.resname))
                        print('{0} {1} {2} {3}'.format(a1.name, a2.name, a3.name, a4.name, func))
                        print('{0} {1} {2} {3}'.format(a1.atomtype, a2.atomtype, a3.atomtype, a4.atomtype))
                        print('{0} {1} {2} {3}'.format(a1.type, a2.type, a3.type, a4.type))
                        print('{0} {1} {2} {3}'.format(a1.atomtypeB, a2.atomtypeB, a3.atomtypeB, a4.atomtypeB))
                        print('{0} {1} {2} {3}'.format(a1.typeB, a2.typeB, a3.typeB, a4.typeB))
                        print('{0}'.format(d))
                        sys.exit(1)

                    # the previous two if sentences will kill the execution
                    # if anything goes wrong. Therefore, I am not afraid to do
                    # d.append() already in the previous steps


    topol.dihedrals.extend(dih9)
    if verbose is True:
        print('log_> Making dihedrals for state B -> %d dihedrals with perturbed atoms' % count)
        print('log_> Removed %d fake dihedrals' % nfake)


def _check_dih_ILDN_OPLS(topol, rlist, rdic, a1, a2, a3, a4):
    counter = 0
    for r in rlist:
        if r.id == a2.resnr:
            dih = rdic[r.resname][3]
            for d in dih:
                if counter == 1:
                    break
                al = []
                for name in d[:4]:
                    atom = r.fetch(name)[0]
                    al.append(atom)

                if (a1.id == al[0].id and a2.id == al[1].id and
                   a3.id == al[2].id and a4.id == al[3].id) or \
                   (a1.id == al[3].id and a2.id == al[2].id and
                   a3.id == al[1].id and a4.id == al[0].id):
                    # ---------------
                    # checks for OPLS
                    # ---------------
                    if d[4].startswith('dih_') and d[5].startswith('dih_'):
                        counter = 42
                        break
                    elif d[4].startswith('dih_') and 'un' in d[5]:
                        counter = 2
                        break
                    elif 'un' in d[4] and d[5].startswith('dih_'):
                        counter = 3
                        break
                    # ---------------
                    # checks for ILDN
                    # ---------------
                    if d[4].startswith('torsion') and d[5].startswith('torsion'):
                        counter = 42
                        break
                    elif d[4].startswith('torsion') and 'un' in d[5]:
                        counter = 2
                        break
                    elif 'un' in d[4] and d[5].startswith('torsion'):
                        counter = 3
                        break
                    elif 'un' in d[4]:
                        counter = 1
                        break
    return counter


def _is_dih_undef(visited_dih, d):
    encountered = 0
    undef = 0
    for dih in visited_dih:
        if (dih[0].id == d[0].id and dih[1].id == d[1].id
           and dih[2].id == d[2].id and dih[3].id == d[3].id):
            if (dih[-1] == 'undefA'):
                undef = 1
                break
            elif (dih[-1] == 'undefB'):
                undef = 2
                break
            elif (dih[-1] == 'undefA_ildn'):
                undef = 3
                break
            elif (dih[-1] == 'undefB_ildn'):
                undef = 4
                break
            else:
                encountered = 1
                break

    return (undef, encountered)


def _is_dih_encountered_strict(visited_dih, d, encountered):
    for dih in visited_dih:
        if (dih[0].id == d[0].id and dih[1].id == d[1].id
           and dih[2].id == d[2].id and dih[3].id == d[3].id):
            encountered = 1
            break
    return encountered


def _get_torsion_multiplicity(name):
    foo = list(name)
    mult = int(foo[-1])
    return mult


def _explicit_defined_dihedrals(filename, ff):
    """ get the #define dihedral entries explicitly for ILDN
    """
    lines = open(filename).readlines()
    output = {}
    ffnamelower = ff.lower()
    for line in lines:
        if line.startswith('#define'):
            entr = line.split()
            name = entr[1]
            if ffnamelower.startswith('amber'):
                params = [9, float(entr[2]), float(entr[3]), int(entr[4])]
            elif ffnamelower.startswith('opls'):
                if len(entr) == 8:  # dihedral
                    params = [3, float(entr[2]), float(entr[3]), float(entr[4]),
                              float(entr[5]), float(entr[6]), float(entr[7])]
                elif len(entr) == 5:
                    params = [1, float(entr[2]), float(entr[3]), float(entr[4])]
            output[name] = params
    return output


def _is_ildn_dih_encountered(ildn_used, d, encountered):
    for dih in ildn_used:
        if (dih[0] == d[0] and dih[1] == d[1] and dih[2] == d[2]
           and dih[3] == d[3] and dih[4] == d[4]):
            encountered = 1
    return encountered


def _find_predefined_dihedrals(topol, rlist, rdic, ffbonded,
                               dih_predef_default, ff):

    dih9 = []  # here I will accumulate multiple entries of type 9 dihedrals
    explicit_def = _explicit_defined_dihedrals(ffbonded, ff)
    ildn_used = []  # ildn dihedrals that already were encountered
    opls_used = []  # opls dihedrals that already were encountered

    for r in rlist:
        idx = r.id - 1
        dih = rdic[r.resname][3]
        imp = rdic[r.resname][2]
        for d in imp+dih:
            al = []
            for name in d[:4]:
                if name.startswith('+'):
                    next = r.chain.residues[idx+1]
                    atom = next.fetch(name[1:])[0]
                    al.append(atom)
                elif name.startswith('-'):
                    prev = r.chain.residues[idx-1]
                    atom = prev.fetch(name[1:])[0]
                    al.append(atom)
                else:
                    atom = r.fetch(name)[0]
                    al.append(atom)

            for dx in topol.dihedrals:
                func = dx[4]
                if (dx[0].id == al[0].id and
                   dx[1].id == al[1].id and
                   dx[2].id == al[2].id and
                   dx[3].id == al[3].id) or \
                   (dx[0].id == al[3].id and
                   dx[1].id == al[2].id and
                   dx[2].id == al[1].id and
                   dx[3].id == al[0].id):
                    # the following checks are needed for amber99sb*-ildn
                    # do not overwrite proper (type9) with improper (type4)
                    if 'default-star' in d[4] and dx[4] == 9:
                        continue
                    # is the dihedral already found for ILDN
                    encountered = 0
                    foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[4]]
                    encountered = _is_ildn_dih_encountered(ildn_used, foobar, encountered)
                    foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[5]]
                    encountered = _is_ildn_dih_encountered(ildn_used, foobar, encountered)
                    if encountered == 1:
                        continue
                    if 'tors' in d[4]:
                        if 'tors' not in dx[5]:
                            continue

                    # check for opls
                    encountered = 0
                    foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[4]]
                    encountered = _is_ildn_dih_encountered(opls_used, foobar, encountered)
                    foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[5]]
                    encountered = _is_ildn_dih_encountered(opls_used, foobar, encountered)
                    if encountered == 1:
                        continue
                    if 'dih_' in d[4]:
                        if 'dih_' not in dx[5]:
                            continue

                    A, B = _check_case(al[:4])
                    paramA = topol.BondedParams.get_dihedral_param(al[0].type,
                                                                   al[1].type,
                                                                   al[2].type,
                                                                   al[3].type,
                                                                   func)
                    paramB = topol.BondedParams.get_dihedral_param(al[0].typeB,
                                                                   al[1].typeB,
                                                                   al[2].typeB,
                                                                   al[3].typeB,
                                                                   func)

                    astate = []
                    bstate = []
                    backup_dx = dx[:]
                    backup_dx2 = dx[:]

                    if d[4] == 'default-A':  # amber99sb
                        if 'un' in d[5]:
                            backup_dx2.append('undefB')
                        dih_predef_default.append(backup_dx2)
                        astate = paramA
                    elif d[4] == 'default-B':  # amber99sb
                        if 'un' in d[5]:
                            backup_dx2.append('undefB')
                        dih_predef_default.append(backup_dx2)
                        astate = paramB
                    elif d[4] == 'default-star':  # amber99sb*
                        foo = [4, 105.4, 0.75, 1]
                        astate.append(foo)
                    elif d[4].startswith('torsion_'):  # amber99sb-ildn
                        if 'un' in d[5]:
                            backup_dx2.append('undefB_ildn')
                        dih_predef_default.append(backup_dx2)
                        foo = explicit_def[d[4]]
                        astate.append(foo)
                        foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[4]]
                        ildn_used.append(foobar)
                        func = 9
                    elif d[4].startswith('dih_'):  # opls proper
                        if 'un' in d[5]:
                            backup_dx2.append('undefB')
                        dih_predef_default.append(backup_dx2)
                        foo = explicit_def[d[4]]
                        astate.append(foo)
                        foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[4]]
                        opls_used.append(foobar)
                        func = 3
                    elif d[4].startswith('improper_'):  # opls improper
                        if 'un' in d[5]:
                            backup_dx2.append('undefB')
                        dih_predef_default.append(backup_dx2)
                        foo = explicit_def[d[4]]
                        astate.append(foo)
                        foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[4]]
                        opls_used.append(foobar)
                        func = 1
                    elif 'un' in d[4]:  # amber99sb-ildn and opls and others
                        if d[5].startswith('torsion_'):
                            backup_dx2.append('undefA_ildn')
                        else:
                            backup_dx2.append('undefA')
                        dih_predef_default.append(backup_dx2)
                        astate = ''
                    else:
                        astate = d[4]

                    if d[5] == 'default-A':  # amber99sb
                        bstate = paramA
                    elif d[5] == 'default-B':  # amber99sb
                        bstate = paramB
                    elif d[5] == 'default-star':  # amber99sb*
                        foo = [4, 105.4, 0.75, 1]
                        bstate.append(foo)
                    elif d[5].startswith('torsion_'):  # amber99sb-ildn
                        foo = explicit_def[d[5]]
                        bstate.append(foo)
                        foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[5]]
                        ildn_used.append(foobar)
                        func = 9
                    elif d[5].startswith('dih_'):  # opls proper
                        foo = explicit_def[d[5]]
                        bstate.append(foo)
                        foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[5]]
                        opls_used.append(foobar)
                        func = 3
                    elif d[5].startswith('improper_'):  # opls improper
                        foo = explicit_def[d[5]]
                        bstate.append(foo)
                        foobar = [dx[0].id, dx[1].id, dx[2].id, dx[3].id, d[5]]
                        ildn_used.append(foobar)
                        func = 1
                    elif 'un' in d[5]:  # amber99sb-ildn and opls and others
                        bstate = ''
                    else:
                        bstate = d[5]

                    # A state
                    counter = 0
                    for foo in astate:
                        if counter == 0:
                            dx[4] = func
                            dx[5] = foo
                            if(func == 3):
                                bar = [foo[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                            elif(func == 2):
                                bar = [foo[0], foo[1], 0.0]
                            else:
                                bar = [foo[0], foo[1], 0.0, foo[-1]]
                            dx.append(bar)
                        else:
                            alus = backup_dx[:]
                            alus[5] = foo
                            if func == 3:
                                bar = [foo[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                            elif(func == 2):
                                bar = [foo[0], foo[1], 0.0]
                            else:
                                bar = [foo[0], foo[1], 0.0, foo[-1]]
                            alus.append(bar)
                            dih9.append(alus)
                        counter = 1

                    # B state
                    for foo in bstate:
                        if counter == 0:
                            dx[4] = func
                            if(func == 3):
                                bar = [foo[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                            elif(func == 2):
                                bar = [foo[0], foo[1], 0.0]
                            else:
                                bar = [foo[0], foo[1], 0.0, foo[-1]]
                            dx[5] = bar
                            dx.append(foo)
                        else:
                            alus = backup_dx[:]
                            if(func == 3):
                                bar = [foo[0], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                            elif(func == 2):
                                bar = [foo[0], foo[1], 0.0]
                            else:
                                bar = [foo[0], foo[1], 0.0, foo[-1]]
                            alus[5] = bar
                            alus.append(foo)
                            dih9.append(alus)
                        counter = 1

    topol.dihedrals.extend(dih9)


def _get_hybrid_residue(residue_name, mtp_file='ffamber99sb.mtp',
                        version='new', verbose=False):
    if verbose is True:
        print('log_> Scanning database for %s ' % residue_name)
    resi, bonds, imps, diheds, rotdic = read_mtp_entry(residue_name,
                                                       filename=mtp_file,
                                                       version=version)
    if len(resi.atoms) == 0:
        raise mtpError("Hybrid residue %s not found in %s"
                       % (residue_name, mtp_file))
    return resi, bonds, imps, diheds, rotdic


def _get_hybrid_residues(m, ff, version='new', verbose=False):
    rdic = {}
    rlist = []
    for res in m.residues:
        if res.is_hybrid():
            rlist.append(res)
            # get topol params for hybrid
            mtp_file = get_mtp_file(res, ff)
            mtp = _get_hybrid_residue(residue_name=res.resname,
                                      mtp_file=mtp_file,
                                      version=version,
                                      verbose=verbose)
            rdic[res.resname] = mtp
            hybrid_res = mtp[0]
            atom_names = list(map(lambda a: a.name, hybrid_res.atoms))
            atoms = res.fetchm(atom_names)
            for i, atom in enumerate(hybrid_res.atoms):
                atoms[i].atomtypeB = atom.atomtypeB
                atoms[i].qB = atom.qB
                atoms[i].mB = atom.mB
    return rlist, rdic


def _add_extra_DNA_RNA_impropers(topol, rlist, func_type, stateA, stateB):
    extra_impropers = []
    for r in rlist:
        if r.resname in ['DAT', 'DAC', 'DGC', 'DGT', 'RAU', 'RAC', 'RGC', 'RGU']:
            print('Adding extra improper dihedrals for residue %d-%s'
                  % (r.id, r.resname))
            alist = r.fetchm(['C1\'', 'N9', 'C8', 'DC2'])
            extra_impropers.append(alist)
            alist = r.fetchm(['C1\'', 'N9', 'C4', 'DC6'])
            extra_impropers.append(alist)
        elif r.resname in ['DTA', 'DTG', 'DCG', 'DCA', 'RUA', 'RUG', 'RCG', 'RCA']:
            print('Adding extra improper dihedrals for residue %d-%s'
                  % (r.id, r.resname))
            alist = r.fetchm(['C1\'', 'N1', 'C6', 'DC4'])
            extra_impropers.append(alist)
            alist = r.fetchm(['C1\'', 'N1', 'C2', 'DC8'])
            extra_impropers.append(alist)
    for imp in extra_impropers:
        imp.extend([func_type, [func_type]+stateA, [func_type]+stateB])
    topol.dihedrals += extra_impropers


# ==============
# Data/Libraries
# ==============
_dna_names = {
    'DA5_DT5': 'D5K',
    'DA5_DC5': 'D5L',
    'DA5_DG5': 'D5M',
    'DT5_DA5': 'D5N',
    'DT5_DC5': 'D5O',
    'DT5_DG5': 'D5P',
    'DC5_DA5': 'D5R',
    'DC5_DT5': 'D5S',
    'DC5_DG5': 'D5T',
    'DG5_DA5': 'D5X',
    'DG5_DT5': 'D5Y',
    'DG5_DC5': 'D5Z',
    'DA3_DT3': 'D3K',
    'DA3_DC3': 'D3L',
    'DA3_DG3': 'D3M',
    'DT3_DA3': 'D3N',
    'DT3_DC3': 'D3O',
    'DT3_DG3': 'D3P',
    'DC3_DA3': 'D3R',
    'DC3_DT3': 'D3S',
    'DC3_DG3': 'D3T',
    'DG3_DA3': 'D3X',
    'DG3_DT3': 'D3Y',
    'DG3_DC3': 'D3Z',
    # False names to avoid an error
    'DG3_DG3': 'FOO',
    'DC3_DC3': 'FOO',
    'DA3_DA3': 'FOO',
    'DT3_DT3': 'FOO',
    'DG5_DG5': 'FOO',
    'DC5_DC5': 'FOO',
    'DA5_DA5': 'FOO',
    'DT5_DT5': 'FOO',
    }

_rna_names = {
    'RA5_RU5': 'R5K',
    'RA5_RC5': 'R5L',
    'RA5_RG5': 'R5M',
    'RU5_RA5': 'R5N',
    'RU5_RC5': 'R5O',
    'RU5_RG5': 'R5P',
    'RC5_RA5': 'R5R',
    'RC5_RU5': 'R5S',
    'RC5_RG5': 'R5T',
    'RG5_RA5': 'R5X',
    'RG5_RU5': 'R5Y',
    'RG5_RC5': 'R5Z',
    'RA3_RU3': 'R3K',
    'RA3_RC3': 'R3L',
    'RA3_RG3': 'R3M',
    'RU3_RA3': 'R3N',
    'RU3_RC3': 'R3O',
    'RU3_RG3': 'R3P',
    'RC3_RA3': 'R3R',
    'RC3_RU3': 'R3S',
    'RC3_RG3': 'R3T',
    'RG3_RA3': 'R3X',
    'RG3_RU3': 'R3Y',
    'RG3_RC3': 'R3Z',
    # False names to avoid an error
    'RG3_RG3': 'FOO',
    'RC3_RC3': 'FOO',
    'RA3_RA3': 'FOO',
    'RU3_RU3': 'FOO',
    'RG5_RG5': 'FOO',
    'RC5_RC5': 'FOO',
    'RA5_RA5': 'FOO',
    'RU5_RU5': 'FOO',
    }
