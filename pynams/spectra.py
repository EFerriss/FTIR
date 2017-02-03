"""
Code for processing and plotting FTIR spectra.

The central concept is an object class called Spectrum, which contains
relevant attributes and methods.

A few defaults are set up that are geared toward H in nominally anhydrous
minerals (NAMs) such a plotting wavenumber range from 3000 to 4000 /cm and
creating baselines between 3200 and 3700 /cm. 

@author Elizabeth Ferriss

"""
from __future__ import print_function, division, absolute_import
import numpy as np
import os
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pynams.styles as styles
import scipy.interpolate as interp
import pandas as pd
#from .uncertainties import ufloat
from uncertainties import ufloat
from . import pynams
from mpl_toolkits.axes_grid1.parasite_axes import SubplotHost
#import diffusion
import gc
#import matplotlib.lines as mlines
#from .uncertainties import ufloat
#from mpl_toolkits.axes_grid1.parasite_axes import SubplotHost
#import matplotlib.gridspec as gridspec
#from matplotlib.ticker import MultipleLocator
#import string as string
#import lmfit
#import uncertainties
#from matplotlib.backends.backend_pdf import PdfPages
#import xlsxwriter
#import json
from scipy import signal as scipysignal

class Spectrum():
    """
    For plotting and manipulating Fourier transform infrared (FTIR) spectra.
    
    Requires an fname, which is the first part of the FTIR filename, e.g.,
    if your raw FTIR spectrum is saved in C:my_folder as my_file.CSV,
    the fname is 'my_file' and the filetype='.CSV'. The folder should be 
    set to 'C:my_folder'. The fname is critical both for locating your file
    and importing your data and because it is used as the default heading and 
    label for a lot of the plotting functions, so it is required. 
    The simplest call would look like this:
        my_spectrum = Spectrum('test_spectrum')
    
    The folder defaults to the present working directory, but you'll 
    probably need to set the folder explicitly using a string like this one:
        'C:\\Users\\Ferriss\\Documents\\Code\\olivine\\'

    The filetype defaults to .CSV, and that's the filetype this code handles
    best, although it's done ok with .txt. 
        
    Once you make your Spectrum, it will automatically open the file and read 
    in the wavenumbers and absorbances. There is a test file test.CSV in 
    the pynams folder.
    
    Use the bound method plot_spectrum() to plot the spectrum, e.g.,
    my_spectrum.plot_spectrum()
    
    The sample thickness can be input in the following ways: 
        1. You can set thickness in microns directly as a keyword when you
           make the Spectrum:
               Spectrum(fname, thickness_microns=x)
               
        2. You can specify a sample, a pynams Sample object, 
           that has thickness information input as thickness_thinslab_microns:
               Spectrum(fname, sample=my_sample)
               
        3. By specifying a sample, a pynams Sample object, that has 
           length information in at least one direction AND specifying the 
           raypath as 'a', 'b', or 'c' or the equivalent 'x', 'y', or 'z'.
           The thickness is then set the as the length of the Sample parallel 
           to the raypath. If the raypath is None (the default) or 'u', it
           acts like Example #2 above in using whatever is set as the sample's
           thickness_thinslab_microns.
           
        4. You can have it guess the thickness based on the Si-O overtones,
           by calling the bound method get_thickness_from_SiO():
               my_spectrum.get_thickness_from_SiO()
    
    The baseline is by default a line between wavenumbers 3200 cm-1 
    (base_low_wn) and 3700 (base_high_wn), and a quadratic baseline would
    deviate from that line relative to base_mid_wn in the middle. Those 
    values can be most easily set under make_baseline for an individual
    spectra, but for handling whole profiles at a time, it's convenient
    to be able to set these attributes and then be able to refer to them
    later on.
    """
    def __init__(self, fname, filetype='.CSV', folder='', sample=None,
                 thickness_microns=None, raypath=None, polar=None, 
                 base_low_wn=3200, base_high_wn=3700,
                 base_mid_wn=3550,
                 ):
        """
        Automatically locates the FTIR file and pulls out the wavenumber 
        (wn_full) and raw absorbance data (abs_raw) and sets the 
        thickness_microns attribute if it input directly or as part of a 
        sample. 
        """
        self.fname = fname
        self.folder = folder
        self.sample = sample
        self.base_high_wn = base_high_wn
        self.base_low_wn = base_low_wn
        self.base_mid_wn = base_mid_wn
        self.polar = polar 
        self.filetype = filetype
        self.raypath = raypath        
        
        try:
            self.filename = self.folder + self.fname + self.filetype
            synthetic = False
        except TypeError:
            synthetic = True

        ### Get the wavenumber and absorbance data from the FTIR file
        if synthetic is False:
            if os.path.isfile(self.filename):
                # read in the signal
                if self.filetype == '.CSV':
                    signal = pd.read_csv(self.filename, header=None)
#                    signal = np.loadtxt(self.filename, delimiter=',')
                elif self.filetype == '.txt':
                    try:
                        signal = np.loadtxt(self.filename, delimiter='\t', 
                                            dtype=None) 
                    except ValueError:
                        print('\nProblem reading this file format. Try .CSV')
                else:
                    print('For now only CSV and txt files work.')

                signal = signal.sort_values(by=[0])
                self.wn_full = np.array(signal[0])
                self.abs_raw = np.array(signal[1])
                
                # set up thickness information
                if thickness_microns is not None:
                    self.thickness_microns = thickness_microns
                else:
                    if sample is not None:
                        idx = styles.get_iorient(raypath)
                        self.thickness_microns = sample.thickness_microns[idx]
                    else:
                        self.thickness_microns = None
    #                    print('Warning: the thickness was not set.')
            else:
                print('There is a problem finding the file.')
                print('filename =', self.filename)
    #            print('current working directory = ', os.getcwd())
                print('Maybe check the folder name')

    def plot_spectrum(self, axes=None, style=styles.style_1, offset=0., 
                      label=None, wn_xlim_left=4000., wn_xlim_right=3000., 
                      pad_top=0.1, pad_bot=0., plot_raw=False):
        """
        Produces a plot of the FTIR spectrum, and returns the figure and axes 
        handles. If you don't know what those are, check out this site: 
            http://matplotlib.org/faq/usage_faq.html
        
        If you already have an axis that you want to add a plot onto, set 
        axes=the handle for the pre-existing axes object, e.g.,
            fig, ax = my_spectrum.plot_spectrum()
            my_second_spectrum.plot_spectrum(axes=ax)
        That should produce a single figure with both my_spectrum and 
        my_second_spectrum plotted on top of each other.
        
        The style of the line can be changed using the keyword style and
        passing in a dictionary. There are several preset style dictionaries
        included in pynams.styles, so, for instance, try:
            from pynams import styles
            my_spectrum.plot_spectrum(style=styles.style_lightgreen)
        Note that the axis takes on the x- and y-limits from the last 
        spectrum plotted, and you can change those after plotting using
        ax.set_xlim() and ax.set_ylim(). 
        
        If you want to move a spectrum up or down, use the offset keyword.
        
        If you add a legend to your axes object with ax.legend(), the label
        given to your spectrum will default to the spectrum's fname. If you
        want to use a different label, pass a 'string' for the label keyword.
        
        The x and y axis limits are set by the keywords wn_xlim_left,
        wn_xlim_right, pad_top, and pad_bot, which default to showing the
        4000-3000 cm-1 wavenumber range where O-H stretching peaks show
        up in nominally anhydrous minerals and zoomed in on the spectrum.
        
        The keyword plot_raw clarifies whether or not to plot the raw
        absorbance data or absobance data that has been divided by 
        thickness and offset such that the lowest point between wavenumbers
        4000 and 3000 cm-1 is set equal to 0. The default is plot_raw=False,
        meaning that the thickness-divided-and-offset spectrum will be plotted,
        but if not thickness data are available, then it will revert to
        plotting just the raw absorbance data.
        """
        if plot_raw is True:
            absorbance = self.abs_raw
        else:
            try:
                absorbance = self.abs_full_cm
            except AttributeError:
                self.divide_by_thickness()
                self.start_at_zero()
                try:
                    absorbance = self.abs_full_cm
                except AttributeError:
                    absorbance = self.abs_raw
                    plot_raw = True
                
        if axes is None:
            fig, ax = styles.plot_spectrum_outline(wn_xlim_left=wn_xlim_left,
                                                   wn_xlim_right=wn_xlim_right)
        else:
            fig = None
            ax = axes

        if plot_raw is True:
            ax.set_ylabel('raw absorbance')
        else:
            self.start_at_zero()
            
        if label is None:
            label = self.fname
            
        style_to_use = style.copy()
        style_to_use.update({'label' : label})
        
        ax.plot(self.wn_full, absorbance + offset, **style_to_use)
        
        ax.set_xlim(wn_xlim_left, wn_xlim_right)
        
        ylow, yhigh = styles.ylim_picker(self, wn_xlim_left=wn_xlim_left,
                                         wn_xlim_right=wn_xlim_right, 
                                         pad_top=pad_top, pad_bot=pad_bot)
        ax.set_ylim(ylow, yhigh)
        ax.set_title(self.fname)
        return fig, ax

    def orientation(self, label=None):
        """
        Returns a figure comparing your spectrum in the wavenumber range
        2200-1200 with spectra for oriented olivine with polarized radation
        in different directions to help guess the olivine orientation.
        
        Use label keyword to change the title on your spectrum from the fname.
        
        """
        # get the image from Lemaire et al. 2004
        thisfolder = os.path.dirname(__file__)
        img_file = '\\'.join((thisfolder, 'Lemaire2004Figure1a.png'))
        img=mpimg.imread(img_file)
        
        # set up subplots and figure
        fig = plt.figure()
        ax1 = SubplotHost(fig, 1,2,1)
        ax2 = SubplotHost(fig, 1,2,2)
        fig.add_subplot(ax1)
        fig.add_subplot(ax2)
        
        # show the image
        plt.imshow(img)
        plt.axis('off')
        ax2.set_title('Oriented olivine\nLemaire et al. 2004')
        
        # show the spectrum with the same scale
        wn_high = 2200.
        wn_low = 1200.

        self.plot_spectrum(pad_top=0.4, wn_xlim_left=wn_high, axes=ax1,
                           wn_xlim_right=wn_low, plot_raw=True)
        
        # zoom in on Si overtone areas
        index_lo = (np.abs(self.wn_full-wn_low)).argmin()
        index_hi = (np.abs(self.wn_full-wn_high)).argmin()        
        SiO = self.abs_raw[index_lo:index_hi]
        ax1.set_ylim(min(SiO), max(SiO)+0.2*max(SiO))
        
        # set spectrum title
        if label is None:
            ax1.set_title(self.fname)
        else:
            ax1.set_title(label)

        fig.set_size_inches(8, 4)
        
        ytext = ax1.get_ylim()[1] - 0.1*ax1.get_ylim()[1]
        wns = [2035, 1925, 1840, 1785, 1670, 1600]
        for idx, wn in enumerate(wns):
#            print(wn)
            ax1.plot([wn, wn], ax1.get_ylim(), '-r')
            ax1.text(wn, ytext, str(wn), rotation=90, backgroundcolor='w',
                    va='center', ha='center', fontsize=12)
        
        ax1.set_xlabel('Wavenumber (cm$^{-1}$)')
        plt.tight_layout()
        plt.subplots_adjust(wspace=-0.1)
        return fig

    def get_thickness_from_SiO(self, show_plot=False, printout=False,
                               accept_thickness=True):
        """
        Estimates the sample thickness based on area of the Si-O overtones
        Using Eq 1 of Matveev and Stachel 2007. 
        
        If show_plot is set to True, it will show (and return figure and axes 
        handlles for) a plot of the line under the Si-O overtones showing the 
        area used to estimate the thickness. 
        
        If printout is set to True, then it will also print the exact
        area under that curve.
        
        If accept_thickness=True (default), the spectrum thickness will
        be automatically changed, and the thickness-normalized absorbance
        will be unpdated. Note that this will screw up any previous baselines.
        """
        wn_low = 1625
        wn_high = 2150

        # indices for absorbance of interest
        index_lo = (np.abs(self.wn_full-wn_low)).argmin()
        index_hi = (np.abs(self.wn_full-wn_high)).argmin()        

        # raw absorbance over Si-O overtones
        SiO_overtones = self.abs_raw[index_lo:index_hi]
        
        # temporary linear baseline under Si-O overtones
        bline = self.make_baseline(wn_low=wn_low, 
                                   wn_high=wn_high, 
                                   show_plot=show_plot,
                                   raw_data=True, 
                                   store_baseline=False
                                   )
        dx = wn_high - wn_low
        dy = np.mean(SiO_overtones - bline)
        SiOarea = dx * dy
        thickness_microns = SiOarea / 0.6366
        
        if accept_thickness is True:
            self.thickness_microns = thickness_microns
            self.divide_by_thickness()
            self.start_at_zero()
        return thickness_microns
#
    def find_lowest_wn_over_given_range(self, wn_mid_range_high=3500., 
                                        wn_mid_range_low=3300.,
                                        relative=True):
        """
        Take a spectrum and wavenumber range (default 3300-3500 cm-1)
        and returns the wavenumber with the lowest absorbance within that range
        """
        if self.abs_full_cm is None:
            self.start_at_zero()
    
        ## find minimum relative to a linear baseline
        if relative is True:            
            self.make_baseline(linetype='line', show_plot=False)
            idx_mid_high = (np.abs(self.base_wn-wn_mid_range_high)).argmin()
            idx_mid_low = (np.abs(self.base_wn-wn_mid_range_low)).argmin()
            if idx_mid_high == idx_mid_low:
                print('basenumber range not established. Check wavenumber range')
                return False
        
            abs_nobase = self.subtract_baseline()
            mid_abs_range = abs_nobase[idx_mid_low:idx_mid_high]
            
            mid_wn_range = self.base_wn[idx_mid_low:idx_mid_high]
            idx_abs_mid = mid_abs_range.argmin()
            WN_MID = mid_wn_range[idx_abs_mid]

        else:        
            ## finds absolute minimum over range
            idx_mid_high = (np.abs(self.wn_full-wn_mid_range_high)).argmin()
            idx_mid_low = (np.abs(self.wn_full-wn_mid_range_low)).argmin()
            mid_abs_range = self.abs_full_cm[idx_mid_low:idx_mid_high]
            mid_wn_range = self.wn_full[idx_mid_low:idx_mid_high]
            idx_abs_mid = mid_abs_range.argmin()
            WN_MID = mid_wn_range[idx_abs_mid]

        return WN_MID
    

    def find_peaks(self, sensitivity=40, show_plot=True, printout=False):
        """
        Returns wavenumbers of the most prominent peaks in wavenumber range of 
        the existing baseline. 
        
        Play with the sensivitity keyword (default=40) to change how many
        peaks it picks up. Higher sensitivity gives you fewer peaks - sorry.
        """
        abs_nobase_cm = self.subtract_baseline()
        if abs_nobase_cm is None:
            return
            
        widths = np.arange(1, sensitivity)
        peaks = scipysignal.find_peaks_cwt(abs_nobase_cm, widths)
        
        if printout is True:
            print('peaks found at the following wavenumbers:')
            print(self.base_wn[peaks])
            print('change sensitivity to find more or fewer peaks')

        if show_plot is True:
            fig, ax = self.plot_subtractbaseline()
            for idx in peaks:
                wn = self.base_wn[idx]
                ax.plot([wn, wn], ax.get_ylim(), '-r', linewidth=1.5)        

        return self.base_wn[peaks]
        
    def make_average_spectra(self, spectra_list, folder=None):
        """Takes list of spectra and returns average absorbance (/cm)
        to the new spectrum (self)"""       
        list_abs_to_average = []
        list_wn = []
        for sp in spectra_list:
            abs_to_append = sp.abs_raw
            list_abs_to_average.append(abs_to_append)
            list_wn.append(sp.wn_full)
        ave_abs = np.mean(list_abs_to_average, axis=0)
        waven = np.mean(list_wn, axis=0)
        self.wn_full = waven
        self.abs_raw = ave_abs
        self.thickness_microns = None
    
    def divide_by_thickness(self):
        """
        Divide raw absorbance by thickness
        """
        # Convert from numpy.float64 to regular python float
        # or else element-wise division doesn't work.
        try:
            if isinstance(self.thickness_microns, float) is True:
                th = self.thickness_microns
            elif isinstance(self.thickness_microns, int) is True:
                th = float(self.thickness_microns)
            else:
                th = np.asscalar(self.thickness_microns)
        except AttributeError:
            print('Need a thickness estimate.')
            print('You could try Spectrum.get_thickness_from_SiO')
            return False
            
        self.abs_full_cm = self.abs_raw * 1e4 / th
        return self.abs_full_cm

    def start_at_zero(self, wn_xlim_left=4000., wn_xlim_right=3000.):
        """
        Divide the raw FTIR absorbance by thickness and
        shift minimum to 0 within specified wavenumber range specified
        by wn_xlim_left and _right
        """
        index_lo = (np.abs(self.wn_full-wn_xlim_right)).argmin()
        index_hi = (np.abs(self.wn_full-wn_xlim_left)).argmin()
        indices = list(range(index_lo, index_hi, 1))

        try: 
            self.abs_full_cm = self.abs_full_cm - min(self.abs_full_cm[indices])
        except AttributeError:
            self.divide_by_thickness()
            try:
                self.abs_full_cm = self.abs_full_cm - min(self.abs_full_cm[indices])
            except AttributeError:
                return
        except ValueError:
            print('There was a problem.')
            print('index_lo at wn', wn_xlim_right, ':', index_lo)
            print('index_hi at wn', wn_xlim_left, ':', index_hi)
            return False
        return self.abs_full_cm
#
    def make_baseline(self, 
                      raw_data=False, 
                      wn_low=3200, 
                      wn_high=3700, 
                      wn_mid=3550,
                      linetype='line', 
                      spline_type='quadratic', 
                      curvature=None, 
                      force_quadratic_through_wn=None,
                      show_fit_values=False, 
                      show_plot=False,
                      abs_high=None, 
                      abs_low=None,
                      abs_smear_high=0, 
                      abs_smear_low=0,
                      store_baseline=True
                      ):
        """
        Makes and returns a baseline under the curve of an FTIR spectrum. 
        
        The spectrum can be either the raw absorbance (raw_data=True) or 
        the default, which uses the absorbance that has already been
        normalized to thickness and offset to start at zero in the O-H
        stretching wavenumber range.
        
        The default baseline is between wavenumbers 3200 and 3700 cm-1.
        Change this range by changing the keywords wn_low and wn_high.
        
        The default shape of the baseline is a line (linetype='line'),
        but you can also do quadratic or spline.  
        
        For quadratics, extent of curvature is determined primarily
        by the keyword curvature, which sets how much to deviate from
        the line between wn_low and wn_high.
        
        Alternatively, set force_quadratic_through_wn, and a quadratic
        will be fit through the absorbance at the wavenumber(s) input in cm-1.
        You can pass in a single wavenumber or a list of wavenumbers.

        For noisy data, try setting abs_smear_high and low to fit to 
        average absorbances around wn_low and wn_high. 10 is usually a 
        good number.
        
        I've had problems with the spline, maybe it's not implemented 
        correctly? My computer tends to take a *really* long time to 
        come up with the spline, so use that one with caution. I think 
        Dan Rasmussen has had better success with it. You can also set 
        the spline_type, which defaults to 'quadratic'. 
        
        and return baseline absorption curve. Shiftline value determines
        how much quadratic deviates from linearity
        """
        # get raw or normalized absorbance
        if raw_data is True:
            absorbance = self.abs_raw
        else:
            try:
                absorbance = self.abs_full_cm
            except AttributeError:
                try:
                    self.start_at_zero()
                    absorbance = self.abs_full_cm
                except AttributeError:
                    print('Spectrum has no thickness_microns attribute')
                    print('Either set raw_data=True or provide thickness')
                    return
        
        # get wavenumber range for baseline
        index_lo = (np.abs(self.wn_full-wn_low)).argmin()
        index_hi = (np.abs(self.wn_full-wn_high)).argmin()        
        base_wn = self.wn_full[index_lo:index_hi]

        # Smearing start and stop over a range of wavenumbers
        abs_smear_high=int(abs_smear_high)
        abs_smear_low=int(abs_smear_low)
        if abs_high is None:
            if abs_smear_high > 0:
                gulp_hi_x = list(range(index_hi-abs_smear_high, 
                                  index_hi+abs_smear_high))
                gulp_hi_y = absorbance[gulp_hi_x]
                yhigh = np.mean(gulp_hi_y)
            else:
                yhigh = absorbance[index_hi]
        else:
            yhigh = abs_high            
        if abs_low is None:
            if abs_smear_low > 0:
                gulp_lo_x = list(range(index_lo-abs_smear_low, 
                                       index_lo+abs_smear_low))
                gulp_lo_y = absorbance[gulp_lo_x]
                ylow = np.mean(gulp_lo_y)
            else:
                ylow = absorbance[index_lo]
        else: 
            ylow = abs_low

        x = np.array([self.wn_full[index_hi], self.wn_full[index_lo]])
        y = np.array([yhigh, ylow])
        try:
            p = np.polyfit(x, y, 1)
        except ValueError:
            print(self.fname)
            print('failed to create a line across wavenumber range')
            print('wavenumbers:', x)
            print('absorbances:', y)
            return
        
        if curvature is not None or force_quadratic_through_wn is not None:
            linetype = 'quadratic'
        
        if linetype == 'line':
            base_abs = np.polyval(p, base_wn)

        elif linetype == 'quadratic':            
            if force_quadratic_through_wn is not None:
                if isinstance(force_quadratic_through_wn, list):
                    xadd = []
                    yadd = []
                    for forcewn in force_quadratic_through_wn:
                        index_mid = (np.abs(self.wn_full - forcewn)).argmin()
                        abs_at_wn_mid = absorbance[index_mid]
                        xadd.append(forcewn)
                        yadd.append(abs_at_wn_mid)
                else:                        
                    try:
                        forcewn = force_quadratic_through_wn
                        index_mid = (np.abs(self.wn_full - forcewn)).argmin()
                        abs_at_wn_mid = absorbance[index_mid]
                        xadd = force_quadratic_through_wn
                        yadd = abs_at_wn_mid                    
                    except TypeError:
                        print('force_quadratic_through_wn must be a number, ')
                        print('the wavenumber in cm-1 you want to fit through')
                        print('or a list of wavenumbers')
                        return
            elif curvature is not None:
                yshift = curvature
                xadd = wn_mid
                yadd = np.polyval(p, wn_mid) - yshift

            x = np.insert(x, 1, xadd)
            y = np.insert(y, 1, yadd)
            p2 = np.polyfit(x, y, 2)
            base_abs = np.polyval(p2, base_wn)

            if show_fit_values == True:
                print('fitting x values:', x)
                print('fitting y values:', y)

        elif linetype == 'spline':
            idx_max = self.wn_full.argmax()
            xinterp = np.concatenate((self.wn_full[0:index_lo], 
                                      self.wn_full[index_hi:idx_max]))                                      
            yinterp = np.concatenate((absorbance[0:index_lo], 
                                      absorbance[index_hi:idx_max]))
            f = interp.interp1d(xinterp, yinterp, kind=spline_type)
            base_abs = f(self.base_wn)
        else:
            print("linetype must be 'line', 'quadratic', or 'spline'")
            return
        
        if store_baseline is True:
            self.base_mid_wn = wn_mid
            self.base_high_wn = wn_high
            self.base_low_wn = wn_low
            self.base_abs = base_abs
            self.base_wn = base_wn
        
        if show_plot is True:
            fig, ax = self.plot_spectrum(plot_raw=raw_data, 
                                         style=styles.style_1)
            ax.set_ylim(min(absorbance[index_lo:index_hi]), 
                        max(absorbance[index_lo:index_hi]))
            ax.set_xlim(wn_high, wn_low)
            ax.plot(base_wn, base_abs, '-k')
#            fig, ax = self.plot_showbaseline(abs_baseline=base_abs,
#                                             wn_baseline=base_wn,
#                                             wn_xlim_left=wn_high,
#                                             wn_xlim_right=wn_low)
            
            if show_fit_values is True:
                if abs_smear_high > 0:
                    ax.plot(self.wn_full[gulp_hi_x], 
                            absorbance[gulp_hi_x], '-y', alpha=0.9)
                    
                if abs_smear_low > 0:
                    ax.plot(self.wn_full[gulp_lo_x], 
                            absorbance[gulp_lo_x], '-y', alpha=0.9)
                    
                if linetype == 'spline':
                    ax.plot(self.wn_full[0:index_lo], 
                            absorbance[0:index_lo], '-r')
                    ax.plot(self.wn_full[index_hi:idx_max], 
                            absorbance[index_hi:idx_max], '-r')
                else:
                    ax.plot(x, y, 'ro', alpha=0.4)
                    
        return base_abs

    def subtract_baseline(self, baseline_abs=None, wn_low=None, wn_high=None,
                          show_plot=False, raw_data=False):
        """
        Returns baseline-subtracted absorbance.
        
        First it looks for a baseline that has been passed in directly 
        through base_abs over a wavenumber range from wn_low to wn_high.
        
        Then it looks for a stored baseline in Spectrum.base_abs over
        a wavenumber range stored in Spectrum.base_low_wn and base_high_wn.
        
        If it can't find a baseline, it will make the default line between
        wavenumbers 3200 and 3700 cm-1.
        
        By default tt won't show the plot unless show_plot=True.
        """

        # get wavenumber range in cm-1
        if wn_low is None:
            wn_low = self.base_low_wn # default=3200
        
        if wn_high is None:
            wn_high = self.base_high_wn # default = 3700

        # get baseline absorbance
        if baseline_abs is None:
            try:
                base_abs = self.base_abs
            except AttributeError:
                print('Making default linear baseline')
                print('Use Spectrum.make_baseline for other baseline options')
                base_abs = self.make_baseline(raw_data=raw_data)
        else:
            base_abs = baseline_abs

        if base_abs is None:
            print('No baseline. Try using raw data or check thickness.')
            return
            
        index_lo = (np.abs(self.wn_full-self.base_low_wn)).argmin()
        index_hi = (np.abs(self.wn_full-self.base_high_wn)).argmin()

        absorbance = self.absorbance_picker()
        humps = absorbance[index_lo:index_hi] # just the peaks we care about

        # lengths sometimes don't match up exactly because of rounding
        if len(humps) > len(base_abs):
            ndif = len(humps) - len(base_abs)
            humps = humps[0:-ndif]
        elif len(humps) < len(base_abs):
            ndif = len(base_abs) - len(humps)
            for n in range(ndif):
                humps = np.append(humps, humps[-1])

        abs_nobase_cm = humps - base_abs

        if show_plot is True:
            self.plot_showbaseline()

        self.abs_nobase_cm = abs_nobase_cm
        return abs_nobase_cm

    def get_area_under_curve(self, show_plot=False, raw_data=False,
                             printout=True, numformat='{:.1f}', 
                             baseline_abs=None, baseline_wn=None):
        """
        Returns area under the curve in cm^2.
        
        By default it prints out (printout=True) the fname and area in the
        format specified by numformat, default 1 number after the decimal. 
        
        To plot the baseline at the same time, set show_plot=True.
        
        You can pass in your own baseline through baseline_abs and 
        baseline_wn
        """
        if baseline_wn is None:
            wn_high = self.base_high_wn
            wn_low = self.base_low_wn
        else:
            wn_high = max(baseline_wn)
            wn_low = min(baseline_wn)
            
        abs_nobase_cm = self.subtract_baseline(show_plot=show_plot,
                                               raw_data=raw_data,
                                               baseline_abs=baseline_abs,
                                               wn_low=wn_low, wn_high=wn_high)
        if abs_nobase_cm is None:
            print('Could not generate area. Check baseline.')
            return False
            
        dx = wn_high - wn_low
        dy = np.mean(abs_nobase_cm)
        area = dx * dy
        if printout is True:
            print(self.fname)
            print('area:', numformat.format(area), '/cm^2')
            
        self.area = area
        return area

    def water(self, phase='cpx', calibration='Bell', numformat='{:.1f}',
              printout=True, scale_water=3):
        """
        Returns the area under the curve and an associated water estimate 
        for a single FTIR spectrum.
        
        Takes the are under the curve for the existing baseline, and
        multiplies by the absorption coefficient for the specified phase
        (e.g., 'olivine' or default 'cpx') and calibration (default 'Bell')
        and then multiplies by the scale_water (default 3). 
        
        These estimates are not really to be trusted. See, e.g., Withers 2013.
        """
        area = self.get_area_under_curve(show_plot=False, printout=False)
        w = pynams.area2water(area, phase=phase, calibration=calibration)
                        
        # output for each spectrum
        if printout is True:
            print(self.fname)
            print(''.join(('water: ', numformat.format(w), ' ppm H2O\n *',
                           str(scale_water), ' = ', 
                    numformat.format(w*3.), ' ppm H2O')))
        return w*scale_water

    def save_spectrum(self, delim='\t', file_ending='-per-cm.txt', 
                      folder=None, raw_data=False, printout=True):
        """
        Save entire spectrum divided by thickness to file with headings.
        1st column: wavenumber /cm; 2nd column: absorbance /cm.
        Default is the format ready for upload to PULI database 
        (http://puli.mfgi.hu/), but to save, e.g.,
        a spectrum that is the average of a profile, change the delimiter
        (delim), file_ending to '.CSV', and set raw_data=True if you don't
        want it to normalize to thickness if possible.
        """
        if self.fname is None:
            print('Need .fname to know what to call saved file')
            return

        if raw_data is True:
            absorbance = self.abs_raw
        else:
            try:            
                absorbance = self.abs_full_cm
            except AttributeError:
                self.divide_by_thickness()
                try:
                    absorbance = self.abs_full_cm
                except AttributeError:
                    print('Saving raw absorbances.')
                    absorbance = self.abs_raw
                    
        if folder is None:
            folder = self.folder
            
        abs_filename = ''.join((folder, self.fname, file_ending))
        a = np.transpose(np.vstack((self.wn_full, absorbance)))
        with open(abs_filename, 'w') as abs_file:
            np.savetxt(abs_file, a, delimiter=delim)
        if printout is True:
            print('Saved', abs_filename)
        
    def save_baseline(self, folder=None, delim=',',
                      baseline_ending='-baseline.CSV'):
        """
        Save baseline (and baseline-subtracted) absorbance spectrum 
        (-baseline) to file fname-baseline.CSV in the specified folder. 
        
        The baselines can be retrieved using get_baseline(). 
        Use save_spectrum() to save full wavenumber and -per-cm absorbances,
        which in most cases will already exist but may not in the case of
        averaged or synthetic spectra.
        
        You can save multiple baselines by changing the keyword 
        baseline_ending. 
        
        The default is a CSV file, but the delimiter (delim) can be changed
        along with the file ending in baseline_ending.
        """
        if folder is None:
            folder = self.folder
            
        # getting baseline absorbance
        if self.base_abs is None:
            print('making default linear baseline')
            base_abs = self.make_baseline()
        else:
            base_abs = self.base_abs
            
        # the baseline-subtracted absorbance is also saved in this file
        abs_nobase_cm = self.subtract_baseline()
        
        # name the baseline file
        base_filename = folder + self.fname + baseline_ending
        
        # make headings in the baseline file
        t = ['wavenumber (/cm)', 'baseline value (/cm)', 
             'baseline-subtracted absorbance (/cm)']
        with open(base_filename, 'w') as base_file:
            for item in t:
                base_file.write(item+delim)
            base_file.write('\n')
            
        # write data to baseline file 
        a = np.transpose(np.vstack((self.base_wn, base_abs, abs_nobase_cm)))
        with open(base_filename, 'a') as base_file:
            np.savetxt(base_file, a, delimiter=delim)
            
        print('Saved', base_filename)

    def get_baseline(self, folder=None, delim=',', 
                     baseline_ending='-baseline.CSV'):
        """
        Get baseline saved using save_baseline().
        
        Requires folder for path location and baseline_ending if other
        than '-baseline.CSV'.
        
        Returns baseline absorbances and baseline-subtracted absorbances. 
        Sets the spectrum's base_wn attribute
        """
        if folder is None:
            folder = self.folder
        filename = ''.join((folder, self.fname, baseline_ending))
        if os.path.isfile(filename) is False:
            return
        data = np.genfromtxt(filename, delimiter=',', dtype='float', 
                             skip_header=1)

        print('Got baseline', filename)
        self.base_wn = data[:, 0]
        self.base_abs = data[:, 1]
        self.abs_nobase_cm = data[:, 2]
        self.base_high_wn = max(data[:, 0])
        self.base_low_wn = min(data[:, 0])
        return self.base_abs, self.abs_nobase_cm
        
    def get_3baselines(self, folder=None, delim=',', 
                baseline_ending='-3baselines.CSV'):
        """Returns block of baseline data saved by water_from_spectra()
        d[:,0] = baseline wavenumbers, d[:,1:4] = baselines, 
        d[:,4:7] = baseline-subtracted absorbances"""
        filename = folder + self.fname + baseline_ending
        if os.path.isfile(filename) is False:
            print(' ')
            print(self.fname)            
            print('Run water_from_spectra() with savebaselines=True')
            return
        data = np.genfromtxt(filename, delimiter=',', dtype='float', 
                             skip_header=1)
        return data                            
                
    def make_peakfit(self, sensitivity=40, peak_positions=None,
                     peak_heights=None, peak_widths=None,
                     show_plot=True):
        """
        Fiddle with the peakfits by passing in peak_positions in as a list of
        wavenmbers in cm-1 and/or peak_heights as a list of baseline-subtracted
        peak heights in cm-1, and/or peak_widths as a list of Gaussian peak 
        widths in wavenumbers cm-1.
        
        If there is no peak information passed in, it will guess the
        peak positions using spectrum.find_peaks(), assume a width of 50 
        for all peaks, and take the height as the absorbance at each peak
        position.
        
        If show_plot is True (default), it runs spectrum.plot_showpeakfit()
        and returns the figure and axes handles
        """
        self.subtract_baseline()
        if self.abs_nobase_cm is None:
            return

        if peak_positions is None:
            self.peakpos = self.find_peaks(show_plot=False, printout=False,
                                           sensitivity=sensitivity)
            print('peak positions:', self.peakpos)
        else:
            self.peakpos = [float(i) for i in peak_positions]
            
        
        if peak_widths is None:
            self.peak_widths = np.ones_like(self.peakpos) * 50.
        else:
            self.peak_widths = [float(i) for i in peak_widths]

        if peak_heights is None:                                           
            self.peak_heights = np.ones_like(self.peakpos)
            for idx, wn in enumerate(self.peakpos):
                idx_peak = (np.abs(self.base_wn-wn)).argmin()
                self.peak_heights[idx] = self.abs_nobase_cm[idx_peak]
            print('heights:', self.peak_heights)
        else:
            self.peak_heights = [float(i) for i in peak_heights]
        
        self.numPeaks = len(self.peakpos)
        
        if show_plot is True:
            fig, ax = self.plot_peakfit()
            return fig, ax

    def save_peakfit(self, folder=None, peak_ending='-peakfit.CSV',
                     delim=','):
        """
        Save peakfit information in a file called fname+peak_ending.
        The default peak_ending is '-peakfit.CSV'. Default delimiter (delim)
        for separating values in the file is a comma.
        """
        if folder is None:
            folder = self.folder
            
        filename = folder + self.fname + peak_ending
        
        # make headings in the peakfit file
        t = ['peak position (wavenumber /cm)', 'height (/cm)', 
             'width of gaussian (/cm)']
        with open(filename, 'w') as peak_file:
            for item in t:
                peak_file.write(item+delim)
            peak_file.write('\n')
            
        # write data to peakfit file 
        a = np.transpose(np.vstack((self.peakpos, self.peak_heights, 
                                    self.peak_widths)))
        with open(filename, 'a') as peak_file:
            np.savetxt(peak_file, a, delimiter=delim)
            
        print('Saved', filename)

    def make_peakfit_like(self, spectrum):
        """
        Takes another spectrum and sets this spectrum's peakfit information
        equal to that of that of the other spectrum. 
        """
        self.subtract_baseline()
        self.peakpos = spectrum.peakpos
        self.peak_heights = spectrum.peak_heights
        self.peak_widths = spectrum.peak_widths
        self.numPeaks = spectrum.numPeaks
        self.make_peakareas()

    def get_peakfit(self, folder=None, delim=',', 
                    peak_ending='-peakfit.CSV'):
        """
        Get individual peaks for spectrum from peakfit file, 
        typically fname-peakfit.CSV, but the peak_ending 
        (default='-peakfit.CSV') can be changed. 
        Return curves (assumes Gaussians) and summation.       
        """
        if folder is None:
            folder = self.folder
        filename = folder + self.fname + peak_ending
        if os.path.isfile(filename) is True:
            previous_fit = pd.read_csv(filename)
            # old peakfit files don't have headings
            if len(list(previous_fit)[0]) < 20:
                previous_fit = pd.read_csv(filename, header=None)
            
            headers = list(previous_fit)
            previous_fit = previous_fit.sort_values(by=[headers[0]])
            self.peakpos = np.array(previous_fit[headers[0]])
            self.numPeaks = len(self.peakpos)
            self.peak_heights = np.array(previous_fit[headers[1]])
            self.peak_widths = np.array(previous_fit[headers[2]])
            self.make_peakareas()
            print('Got peak info from', filename)
        else:
            print(' ')            
            print('Unable to get peak info from', filename)
            print('Try spec.make_peakfit')            
        
    def get_gaussians(self):
        """
        Generates Gaussian curves from peakfitting info. 
        
        Requires both peak fitting information and a baseline.
        
        Returns (1) peakfitcurves, all of the individual gaussians,
        and (2) summed_spectrum, the sum of all the peakfitcurvesb
        """
        try:
            peakpos = self.peakpos
        except AttributeError:
            print('No peakfitting information available yet')
            return False, False
        try:
            peakfitcurves = np.ones([len(peakpos), len(self.base_wn)])
        except AttributeError:
            print('Make or get a baseline before getting peakfit')
            return False, False
            
        summed_spectrum = np.zeros_like(self.base_wn)
        for k in range(len(self.peakpos)):
            peakfitcurves[k] = pynams.make_gaussian(x=self.base_wn, 
                                                pos=self.peakpos[k],
                                                h=self.peak_heights[k], 
                                                w=self.peak_widths[k])

            summed_spectrum += peakfitcurves[k]
        return peakfitcurves, summed_spectrum

    def make_peakareas(self):
        """
        Assign peak area based on Gaussian curves from current peak
        width and height
        """
        peakfitcurves, summed_spectrum = self.get_gaussians()
        if peakfitcurves is False:
            return
        else:
            self.peak_areas = np.zeros(len(self.peakpos))
            for k in range(len(self.peakpos)):
                dx = self.base_high_wn - self.base_low_wn
                dy = np.mean(peakfitcurves[k])
                area = dx * dy
                self.peak_areas[k] = area
    
    def make_composite_peak(self, peak_idx_list):
        """Make a new 'peak', e.g., for [Ti] in olivine, by summing up 
        other peaks given by their indexes in peak_idx_list"""
        peakpos_new = 0.
        peak_height_new = 0.
        peak_width_new = 0.
        peak_area_new = 0.
        for idx in peak_idx_list:
            peakpos_new = peakpos_new + self.peakpos[idx]
            peak_height_new = peak_height_new + self.peak_heights[idx]
            peak_width_new = peak_width_new + self.peak_widths[idx]
            peak_area_new = peak_area_new + self.peak_areas[idx]
    

        self.peakpos = np.append(self.peakpos, peakpos_new)
        self.peak_heights = np.append(self.peak_heights, peak_height_new)
        self.peak_widths = np.append(self.peak_widths, peak_width_new)
        self.peak_areas = np.append(self.peak_areas, peak_area_new)
        
    def plot_peakfit(self, style=styles.style_spectrum, 
                     stylesum=styles.style_summed, 
                     axes = None, legend=True,
                     stylepeaks=styles.style_fitpeak, top=None, legloc=1):
        """Single spectrum: Plot peaks fit in MATLAB using peakfit.m
        REQUIRES the peak_ending and baseline_ending so that it can
        locate the file spectrum.fname+peak_ending and +baseline_ending.
        If those aren't present or the file doesn't exist, it will screw 
        up."""
        # Take baseline-subtracted spectrum from saved file every time 
        # to avoid any possible funny business from playing with baselines

        gaussian, summed_spectrum = self.get_gaussians() 
        
        if gaussian is False:
            return False, False
        
        if axes is None:
            try:
                fig, ax = self.plot_subtractbaseline(style=style, label='') 
            except AttributeError:
                print('Remember to make or get baseline')
        else: 
            ax = axes
            
        ax.plot(self.base_wn, self.abs_nobase_cm, label='observed', **style)
        ax.plot(self.base_wn, gaussian[0], label='fit bands', **stylepeaks)
        ax.plot(self.base_wn, summed_spectrum, label='peak sum', **stylesum)
        
        if axes is None:
            if legend is True:
                ax.legend(loc=legloc)
            ax.set_ylim(0., top)        
        
        if top is None:
            topnat = ax.get_ylim()[1]
            top = topnat + topnat*0.75
            

        for k in range(len(self.peakpos)):
            ax.plot(self.base_wn, gaussian[k], **stylepeaks)

        if axes is None:
            fig.set_size_inches(6, 6)
            ax.set_title(self.fname)
            return fig, ax

    def abs_at_given_wn(self, wn, absorbance='thickness normalized'):
        """Input wavenumber, output absorbance that is thickness normalized
        (absorbance='normalized' default), 'raw', or 'baseline-subtracted'"""

        # check you know what the wavenumbers are
        if self.wn_full is None:
            check = self.get_data()
            if check is False:
                return False

        idx = (np.abs(self.wn_full-wn)).argmin()
                
        if absorbance == 'thickness normalized':
            if self.abs_full_cm is None:
                self.start_at_zero()
            abs_at_wn = self.abs_full_cm[idx]
            return abs_at_wn
            
        elif absorbance == 'raw':
            print('Sorry, raw not programmed in yet')
#            if self.abs_raw is None:
#                self.get_data()
            return
        elif absorbance == 'baseline-subtracted':
            print('Sorry, baseline-subtracted not programmed in yet')
            return
        else: 
            print('absorbance options are:')
            print('thickness normalized (default)')
            print('raw')
            print('baseline-subtracted')

    def absorbance_picker(self):
        """Is this raw or thickness normalized absorbance you're after?"""
        if self.thickness_microns is None:
            if self.abs_raw is None:
                self.get_data()
            absorbance = self.abs_raw
        else:
            try:
                absorbance = self.abs_full_cm
            except AttributeError:
                self.start_at_zero()
                absorbance = self.abs_full_cm
        return absorbance            
        
    def plot_showbaseline(self, axes=None, 
                          abs_baseline=None, 
                          wn_baseline=None, 
                          style=styles.style_spectrum, 
                          style_base=styles.style_baseline,
                          label=None, 
                          label_baseline=False,
                          offset=0.0, 
                          wn_xlim_left=4000, 
                          wn_xlim_right=3000.):
        """
        Plot FTIR spectrum and show baseline. 
        
        If axes is set, it will plot on that axes. Otherwise it will create
        and return new figure and axes handles. 
        
        If you have a curve that you want to pass in and use as a baseline,
        the absorbances go into abs_baseline, and the wavenumbers go in
        as wn_baseline. It will draw that baseline first.
        
        If no baseline is passed in explicitly, it will look for a baseline
        that has already been created by Spectrum.make_baseline, which 
        automatically saves the baseline in Spectrum.base_abs (absorbances)
        and Spectrum.base_wn (wavenumbers). 
        
        If no baseline yet exists, it will create the default linear baseline.
        
        You can pass in style dictionaries to change the line style of the
        curve (style) and the baseline (style_base). 
        
        If you later make a legend, the curve will come out labeled as the
        Spectrum.fname (default) or as the label set here. The baseline
        won't show up in the legend unless you set label_baseline=True.
        
        You can move the curve and baseline together up and down with offset.
        
        The default window is from 4000 to 3000 cm-1 wavenumbers and should
        be zoomed in on the curve. You may need to adjust your axes limits
        afterward, particularly when plotting multiple spectra.
        """
        # which axes to plot on
        if axes is None:
            fig, ax = styles.plot_spectrum_outline(wn_xlim_left=wn_xlim_left,
                                                   wn_xlim_right=wn_xlim_right)
        else:
            fig = None
            ax = axes
        
        # Get or make absorbance for baseline
        if abs_baseline is None:
            try:
                abs_baseline = self.base_abs
            except AttributeError:
                print('Making the default linear baseline.')
                print('Use Spectrum.make_baseline for other baselines.')
                abs_baseline = self.make_baseline()

        # get baseline wavenumber range
        if wn_baseline is None:
            if self.base_wn is not None:
                wn_baseline = self.base_wn
            else:
                print(('Need to pass in baseline wavenumber range too ' +
                       'either here as wn_baseline or as spectrum.base_wn'))
                return                

        # labels that would show up in a legend
        if label is None:
            label = self.fname
        style_to_use = style.copy()
        style_to_use.update({'label' : label})
        if label_baseline is True:
            style_base['label'] = 'baseline'

        # Grab thickness-normalized absorbances or raw if no thickness
        absorbance = self.absorbance_picker()

        ax.plot(self.wn_full, absorbance + offset, **style_to_use)
        ax.plot(wn_baseline, abs_baseline + offset, **style_base)
        
        if self.thickness_microns is None:
            ax.set_ylabel('Raw absorbance')

        # zoom in on y-axis
        ylow, yhigh = styles.ylim_picker(self, pad_top=0.2, pad_bot=0.2)
        yhigh = yhigh + 0.1*yhigh
        ax.set_ylim(ylow, yhigh)
            
        return fig, ax

    def plot_subtractbaseline(self, 
                              style=styles.style_spectrum, 
                              axes=None, 
                              label=None, 
                              offset=0.,):
        """
        Make and plot baseline-subtracted spectrum. style, axes, label, and
        offset are the same options as in Spectrum.plot_showbaseline()
        """
        abs_nobase_cm = self.subtract_baseline()
        
        if axes is None:
            fig, ax = styles.plot_spectrum_outline()
        else:
            fig = None
            ax = axes

        if label is None:
            label = self.fname
        style_to_use = style.copy()
        style_to_use.update({'label' : label})
            
        pad = max(abs_nobase_cm)
        yhigh = pad + 0.1*pad
        ax.set_ylim(0, yhigh)
        ax.set_xlim(self.base_high_wn, self.base_low_wn)
        ax.plot(self.base_wn, abs_nobase_cm+offset, **style_to_use)
        ax.set_title(self.fname)
        return fig, ax

    def plot_peakfit_and_baseline(self, style=styles.style_spectrum, 
                                  stylesum=styles.style_summed, 
                                  stylepeaks=styles.style_fitpeak, 
                                  style_base=styles.style_baseline,
                                  top=None, bottom=0., legloc=1, 
                                  label_spectrum='observed', 
                                  peak_ending='-peakfit.CSV',
                                  baseline_ending='-baseline.CSV'):
        """Plot spectrum with baseline and peakfit information together"""
        # Take baseline-subtracted spectrum from saved file every time 
        # to avoid any possible funny business from playing with baselines
        if self.peakpos is None:
            print('need to run get_peakfit first')
            return
        if self.base_wn is None:
            print('need to run get_baseline() first')
            return
        
        gaussian, summed_spectrum = self.get_gaussians(peak_ending=peak_ending, 
                                              baseline_ending=baseline_ending)
            
        wn = self.base_wn

        stylepeaks['zorder'] = 1 # otherwise peaks show up above baseline
        
        fig, ax = self.plot_spectrum(style=style, label=label_spectrum)
        ax.plot(self.base_wn, self.base_abs, label='baseline', **style_base) 
        ax.plot(wn, gaussian[0]+self.base_abs, label='fit bands', **stylepeaks)
        ax.plot(self.base_wn, summed_spectrum+self.base_abs, label='peak sum', 
                **stylesum)
                
        ax.legend(loc=legloc)
        
        if top is None:
            topnat = ax.get_ylim()[1]
            top = topnat + topnat*0.75
            
        ax.set_ylim(bottom, top)

        for k in range(len(self.peakpos)):
            ax.plot(self.base_wn, gaussian[k]+self.base_abs, **stylepeaks)

        return fig, ax

           

def make_filenames(folder, classname=Spectrum, file_ending='.CSV'):
    """ Set filename attribute based on folder and fname attribute
    for all Spectra() with fname but no filename."""
    for obj in gc.get_objects():
        if isinstance(obj, classname):
            try:
                if obj.fname is not None and obj.filename is None:
                    obj.filename = ''.join((folder, obj.fname, file_ending))
            except AttributeError:
                print('just chill, ok?')

def water_from_spectra(list3, folder, phase='cpx', 
                       proper3=False, numformat='{:.0f}',
                       savebaselines=False, show_plots=True, 
                       baseline_ending='-3baselines.CSV', delim=',', 
                       calibration='Bell', main_yshift=None,
                       window_large=None, window_small=None, yhigh=1.):
    """Produce water estimate from list of FTIR spectra; 
    Default calibration is Bell et al. 1995, ideally using 
    3 spectra that are polarized in orthogonal directions (proper3=True)
    Default (proper3=False) is to estimate area and total water from each spectrum.
    Then average and std the results."""
    if calibration == 'Bell':
        print('Bell calibration')
        pass
    elif calibration == 'Paterson':
        print('Paterson calibration not available quite yet...')
        return
    else:
        print('Only Bell (default) or Paterson calibration so far')
        return
        
    if proper3 == True and len(list3) != 3:
        print(' ')
        print('For proper3=True, list should contain only 3 spectra')
        proper3 = False
    
    uarea_list = []
    uwater_list = []
    
    for spec in list3:
        if show_plots is True:
            print('Showing spectrum for', spec.fname)
            fig, ax = spec.plot_spectrum_outline()
            plt.plot(spec.wn_full, spec.abs_full_cm, **styles.style_spectrum) 

        # how much to shift each quadratic line
        if main_yshift is None:        
            main_yshift = spec.base_mid_yshift        
        if window_large is None:
            window_large = spec.base_w_large
        if window_small is None:
            window_small = spec.base_w_small

        if spec.abs_full_cm is None:
            spec.start_at_zero()
        # Generate list of 3 possible areas under the curve
        area_list = np.array([])
        spec.make_baseline()
        baseline_list = np.ones([3, len(spec.base_wn)])
        pek_list = np.ones([3, len(spec.base_wn)])
#        
        k = 0
        for bam in [window_small, -window_small, -window_large]:
            # Setting up 3 different baseline shapes
            main_yshift = main_yshift - bam
            base_abs = spec.make_baseline('quadratic', shiftline=main_yshift)
            abs_nobase_cm = spec.subtract_baseline(bline=base_abs)
            if show_plots is True:
                ax.plot(spec.base_wn, base_abs, **styles.style_baseline)

            area = spec.get_area_under_curve(area_plot=False, printout=False)
            area_list = np.append(area_list, area)
            baseline_list[k,:] = base_abs
            pek_list[k,:] = abs_nobase_cm
            k+=1

        # list areas and water with uncertainties
        uarea = ufloat(np.mean(area_list), np.std(area_list))
        uarea_list.append(uarea)
        uwater = pynams.area2water(uarea, phase=phase)

        # Water estimate depends on if you are adding 3 areas 
        # or just multiplying by three and later averaging
        if proper3 is False:
            uwater = 3*uwater
        uwater_list.append(uwater)

        # I show() the figures explicitly in this first loop because
        # otherwise they show up inline *after* all the printed output
        if show_plots is True:
            if min(base_abs) > 0:
                ylow = 0
            else:
                ylow = min(base_abs) + 0.1*min(base_abs)
            plt.ylim(ylow, yhigh)
            plt.show(fig)

        if savebaselines is True:
            base_filename = folder + spec.fname + baseline_ending
            t = ['wavenumber (/cm)', 'upper baseline (/cm) (smaller area)', 
                 'main baseline (/cm)', 'lower baseline (/cm) (larger area)',
                 'absorbance - upper baseline (/cm)', 
                 'absorbance - main baseline (/cm)',
                 'absorbance - lower baseline (/cm)']
            with open(base_filename, 'w') as base_file:
                for item in t:
                    base_file.write(item+delim)
                base_file.write('\n')
            a = np.transpose(np.vstack((spec.base_wn, baseline_list, pek_list)))
            with open(base_filename, 'a') as base_file:
                np.savetxt(base_file, a, delimiter=delim)
            
    # output for each spectrum
    for x in range(len(list3)):
        print(list3[x].fname)
        print("area:", numformat.format(uarea_list[x]), "/cm^2")
        print("water:", numformat.format(uwater_list[x]), "ppm H2O")
        if savebaselines is True:
            print('Saved baselines to', list3[x].fname+baseline_ending)
        print(' ')
    # Final output
    if proper3 == True:
        a = np.sum(uarea_list)
        w = np.sum(uwater_list)
        print('Sum of individual contributions')
    else:
        a = np.mean(uarea_list)
        w = np.mean(uwater_list)
        print('Averaged individual (*3) estimates')
    print('area:', numformat.format(a), '/cm^2')
    print('water:', numformat.format(w), 'ppm H2O')
    print(' ')
    return a, w  

def list_with_attribute(classname, attributename, attributevalue):
    """Gather all instances in specified class with a particular attribute"""
    my_list = []
    for obj in gc.get_objects():
        if isinstance(obj, classname):
            if getattr(obj, attributename) == attributevalue:
                my_list.append(obj.fname)
    return my_list

