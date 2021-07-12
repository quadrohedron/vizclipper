from os import access as os_acc, F_OK, X_OK
from os.path import join as os_pjoin
from subprocess import Popen, PIPE, STARTUPINFO, STARTF_USESHOWWINDOW
import tkinter as tk
import tkinter.messagebox as tkmsg
import tkinter.ttk as ttk
import tkinter.filedialog as tkfd
import re
import time



DEBUG = False

DEFAULT_PATHS = {
    'C:/Program Files (x86)/Vizrt/Viz3/ev_send.exe' : '3.6',
    'C:/Program Files/Vizrt/Viz3/ev_send.exe'       : '3.14',
    './ev_send/dist/ev_send.exe'                    : 'DBG',
}



class WrappingLabel(ttk.Label):
    def __init__(self, master = None, **kwargs):
        tk.Label.__init__(self, master, **kwargs)
        self.bind('<Configure>', lambda e: self.config(wraplength = self.winfo_width()))

class ReadOnlyText(tk.Text):
    def __init__(self, master = None, **kwargs):
        tk.Text.__init__(self, master, **kwargs)
        self.bind('<Escape>', lambda e: self.master.focus())
        self.bind('<FocusIn>', lambda e: self.master.focus())
        self.bind('<Key>', lambda e: 'break')

class Clipper(ttk.Frame):
    FRAMERATE = 25
    evs_path = './ev_send.exe'
    viz_version = '3.6'
    channel = 1
    state = {
        'connected'     : False,
        #'scene_running' : False,
    }
    head_re = re.compile('^(s|(?:0 )|(?:-1 )?)((?:[GVC]\*)?)([^ ]+)( .+)*$', re.IGNORECASE)

    def __init__(self, root):
        super().__init__(master = root)
        self.root = root
        self.pack(fill = tk.BOTH, expand = 1)
        self.root.resizable(0, 0)
        self.STYLE = ttk.Style()
        #
        self.tStamp, self.tDuration, self.tLimit = None, None, None
        self.ftRec = None
        self.RECRUNNING = False
        self.SCENERUNNING = False
        self.thread_handle = None
        #
        self.RELim = re.compile('^[0-9]*\.?[0-9]*$')
        #
        self.strvars = {k: tk.StringVar(self.master, value = f'<{k}>') for k in (
            'fn', 'dir', 'time', 'log', 'curdur',
            'stat', 'conn', 'lentype', 'reclen',
            'frame', 'sync_delay_val'
        )}
        self.strvars['fn'].set('<filename>')
        self.strvars['dir'].set('<directory>')
        self.strvars['frame'].set('0')
        self.strvars['reclen'].set('10')
        self.strvars['curdur'].set('00:00.00')
        self.strvars['sync_delay_val'].set('0')
        self.intvars = {k: tk.IntVar(self.master) for k in (
            'unlim', 'sync', 'sync_delay_chk',
        )}
        #
        self.params_locked = tk.IntVar(self.master, 0)
        #
        self._llb = False
        self._lli = 0
        self._lll = (38, 40, 37, 39)
        #
        if DEBUG:
            self.master.title('Clipper v0.0 [DEBUG]')
            self.initUI_DEBUG()
        else:
            self.master.title('Clipper v0.0')
            self.initUI()
            self.style_setup()
        self.startup()
        ### Binding logger
        for k in ('<Left>', '<Right>', '<Up>', '<Down>'):
            self.master.bind(k, lambda e: self._lla(e.keycode))
    
    def initUI(self):
        # Labeling panels
        ttk.Label(self, text = 'Clipout Recorder', style = 'h0.TLabel')\
            .grid(row = 1, column = 1, columnspan = 3, sticky='news', ipadx = 10, ipady = 10)
        ttk.Label(self, text = 'Output File Settings', style = 'h1.TLabel')\
            .grid(row = 3, column = 1, sticky='news', ipadx = 5, ipady = 5)
        ttk.Label(self, text = 'Record Length', style = 'h1.TLabel')\
            .grid(row = 3, column = 3, sticky='news', ipadx = 5, ipady = 5)
        ttk.Label(self, text = 'Animation Control', style = 'h1.TLabel')\
            .grid(row = 7, column = 1, sticky='news', ipadx = 5, ipady = 5)
        ttk.Label(self, text = 'Record Control', style = 'h1.TLabel')\
            .grid(row = 7, column = 3, sticky='news', ipadx = 5, ipady = 5)

        # Configuring the grid
        for i in range(0, 11, 2):
            self.rowconfigure(i, minsize = 10, weight = 1)
        for i in range(0, 5, 2):
            self.columnconfigure(i, minsize = 10, weight = 2)
        for i in range(1, 4, 2):
            self.columnconfigure(i, minsize = 10, weight = 1)
        
        # Status bar setup
        sp = ttk.Frame(self)
        sp.grid(row = 11, column = 1, columnspan = 3, sticky = 'news')
        sp.columnconfigure(0, weight = 3)
        sp.columnconfigure(1, weight = 1)
        ttk.Label(sp, textvariable = self.strvars['stat'], style = 'status.TLabel').grid(row = 0, column = 0, sticky = 'nws')
        ttk.Label(sp, textvariable = self.strvars['conn'], style = 'status.TLabel', justify = tk.RIGHT)\
            .grid(row = 0, column = 1, padx = (10, 0), sticky = 'nes')
        
        # Logger setup
        self.LOGTEXT = tk.StringVar(self.master)

        # FP panel
        p0 = ttk.Frame(self)
        p0.grid(row = 5, column = 1, sticky = 'news')
        p0.columnconfigure(0, weight = 1)
        ttk.Label(p0, text = 'Filename:').grid(row = 0, column = 0, sticky = 'news')
        self.weFN = ttk.Entry(p0, textvariable = self.strvars['fn'])
        def weFN_func(event):
            self.focus()
        self.weFN.bind('<Return>', weFN_func)
        self.weFN.grid(row = 1, column = 0, sticky = 'news')
        p1 = ttk.Frame(p0)
        p1.grid(row = 2, column = 0, sticky = 'news')
        ttk.Label(p1, text = 'Directory:').pack(side = 'left')
        ttk.Button(p1, text = 'Browse', command = self.clipdir_dialogue).pack(side = 'right')
        self.weDir = ttk.Entry(p0, textvariable = self.strvars['dir'])
        self.weDir.grid(row = 3, column = 0, sticky = 'news')

        # RL panel
        p0 = ttk.Frame(self)
        p0.grid(row = 5, column = 3, sticky = 'news')
        p0.columnconfigure(0, weight = 1)
        self.wcLenUnlimited = ttk.Checkbutton(
            p0, text = 'Unlimited', style = 'centered.TCheckbutton', variable = self.intvars['unlim']
        )
        self.intvars['unlim'].set(1)
        self.wcLenUnlimited.grid(row = 0, column = 0, sticky = 'ns')
        p1 = ttk.Frame(p0)
        p1.grid(row = 1, column = 0, sticky = 'news')
        p1.columnconfigure(0, weight = 1)
        p2 = ttk.Frame(p1)
        p2.grid(row = 0, column = 0, sticky = 'news')
        p2.columnconfigure(0, weight = 1)
        self.wrLenFrames = ttk.Radiobutton(p2, text = 'Frames', variable = self.strvars['lentype'], value = 'frames')
        self.wrLenFrames.pack(side = 'left', expand = 1)
        self.wrLenSeconds = ttk.Radiobutton(p2, text = 'Seconds', variable = self.strvars['lentype'], value = 'seconds')
        self.strvars['lentype'].set('seconds')
        self.wrLenSeconds.pack(side = 'right', expand = 1)
        validator = self.register(lambda x: not self.RELim.match(x) is None)
        self.weLenVal = ttk.Entry(p1, textvariable = self.strvars['reclen'], validate='all',\
            validatecommand=(validator, '%P'))
        self.weLenVal.grid(row = 1, column = 0)

        # AC panel
        p0 = ttk.Frame(self)
        p0.grid(row = 9, column = 1, sticky = 'news')
        p0.columnconfigure(0, weight = 1)
        p0.rowconfigure(1, weight = 1)
        p1 = ttk.Frame(p0)
        p1.grid(row = 0, column = 0, sticky = 'ns')
        p1.columnconfigure(0, weight = 1)
        ttk.Label(p1, text = 'Go to frame:').grid(row = 0, column = 0, sticky = 'news')
        ttk.Spinbox(p1, from_ = 0, to = 2**16, increment = 1, textvariable = self.strvars['frame'], width = 8)\
            .grid(row = 0, column = 1, sticky = 'news', padx = 10)
        ttk.Button(p1, text = 'Go', command = self.set_frame, state = 'disabled').grid(row = 0, column = 2, sticky = 'news')
        p1 = ttk.Frame(p0)
        p1.grid(row = 1, column = 0, pady = 10, sticky = 'news')
        for i in range(2):
            p1.rowconfigure(i, weight = 1)
            p1.columnconfigure(i, weight = 1)
        ttk.Button(p1, text = 'Reset', command = self.anim_reset, state = 'disabled').grid(row = 0, column = 0, sticky = 'news')
        ttk.Button(p1, text = 'Stop', command = self.anim_stop).grid(row = 0, column = 1, sticky = 'news')
        ttk.Button(p1, text = 'Start', command = self.anim_start, state = 'disabled').grid(row = 1, column = 0, sticky = 'news')
        ttk.Button(p1, text = 'Continue', command = self.anim_cont).grid(row = 1, column = 1, sticky = 'news')
        self.wcSync = ttk.Checkbutton(
            p0, text = 'Synchronize with recording', style = 'centered.TCheckbutton', variable = self.intvars['sync']
        )
        self.intvars['sync'].set(1)
        self.wcSync.grid(row = 2, column = 0, pady = (0, 0), sticky = 'ns')
        p1 = ttk.Frame(p0)
        p1.grid(row = 3, column = 0, sticky = 'news')
        p1.columnconfigure(0, weight = 1)
        self.wcSyncDelay = ttk.Checkbutton(
            p1, text = 'Animation delay:', style = 'centered.TCheckbutton', variable = self.intvars['sync_delay_chk']
        )
        self.wcSyncDelay.grid(row = 0, column = 0, sticky = 'news')
        self.wsSyncDelayVal = ttk.Spinbox(p1, from_ = -60, to = 60, increment = 1, textvariable = self.strvars['sync_delay_val'], width = 8)
        self.wsSyncDelayVal.grid(row = 0, column = 1, padx = 10, sticky = 'news')
        self.wsSyncDelayVal.config(state = tk.DISABLED)
        ttk.Label(p1, text = 'frames').grid(row = 0, column = 2, sticky = 'news')

        # RC panel
        p0 = ttk.Frame(self)
        p0.grid(row = 9, column = 3, sticky = 'news')
        p0.columnconfigure(0, weight = 1)
        p0.rowconfigure(2, weight = 1)
        ttk.Label(p0, text = 'Current recording time:', style = 'centered.TLabel').grid(row = 0, column = 0, sticky = 'news')
        ttk.Label(p0, textvar = self.strvars['curdur'], style = 'timer.TLabel')\
            .grid(row = 1, column = 0, sticky = 'news', pady = 10)
        p1 = ttk.Frame(p0)
        p1.grid(row = 2, column = 0, sticky = 'ew')
        p1.rowconfigure(0, weight = 1)
        p1.columnconfigure(0, weight = 1)
        p1.columnconfigure(1, weight = 1)
        p1.columnconfigure(2, weight = 1)
        self.wbRCI = ttk.Button(p1, text = 'Set\n---\nReset', command = self.rctrl_reset, style = 'rctrl.TButton')
        self.wbRCI.grid(row = 0, column = 0, sticky = 'news')
        self.wbRCR = ttk.Button(p1, text = 'Record', command = self.rctrl_go, style = 'rctrl.TButton')
        self.wbRCR.grid(row = 0, column = 1, sticky = 'news')
        self.wbRCS = ttk.Button(p1, text = 'Stop', command = self.rctrl_stop, style = 'rctrl.TButton')
        self.wbRCS.grid(row = 0, column = 2, sticky = 'news')
        self._manage_wrc('stop')
        #
        self.training_setup(p1)
        
        # Setting up widget state interactions
        def unlim_cb(*args):
            state = 'disabled' if self.intvars['unlim'].get() else 'normal'
            for w in (self.wrLenFrames, self.wrLenSeconds, self.weLenVal):
                w.config(state = state)
        self.intvars['unlim'].trace_add('write', unlim_cb)
        unlim_cb()
        def sync_cb(*args):
            f = self.intvars['sync'].get()
            state = 'normal' if f else 'disabled'
            self.wcSyncDelay.config(state = state)
            state = 'normal' if f and self.intvars['sync_delay_chk'].get() else 'disabled'
            self.wsSyncDelayVal.config(state = state)
        self.intvars['sync'].trace_add('write', sync_cb)
        sync_cb()
        def syncdel_cb(*args):
            state = 'normal' if self.intvars['sync_delay_chk'].get() else 'disabled'
            self.wsSyncDelayVal.config(state = state)
        self.intvars['sync_delay_chk'].trace_add('write', syncdel_cb)
        #
        def param_cb(*args):
            if self.params_locked.get():
                for w in (self.wrLenFrames, self.wrLenSeconds, self.weLenVal, self.wcLenUnlimited, self.wcSyncDelay, self.wsSyncDelayVal):
                    w.configure(state = 'disabled')
            else:
                self.wcLenUnlimited.configure(state = 'normal')
                unlim_cb()
                sync_cb()
        self.params_locked.trace_add('write', param_cb)

        # Log on completion
        self._log('init', 'UI init complete.')

    def initUI_old(self):
        # Make panels
        fp = tk.Frame(self, width = 200, height = 120, bg = '#303030')
        #fp = tk.Frame(self, bg = '#303030')
        fp.grid(row = 0, column = 0, sticky = 'news')
        rl = tk.Frame(self, width = 200, height = 120, bg = '#606060')
        #rl = tk.Frame(self, bg = '#606060')
        rl.grid(row = 0, column = 1, sticky = 'news')
        ac = tk.Frame(self, width = 200, height = 220, bg = '#909090')
        #ac = tk.Frame(self, bg = '#909090')
        ac.grid(row = 1, column = 0, sticky = 'news')
        rp = tk.Frame(self, width = 200, height = 220, bg = '#c0c0c0')
        #rp = tk.Frame(self, bg = '#c0c0c0')
        rp.grid(row = 1, column = 1, sticky = 'news')
        tm = tk.Frame(rp, width = 200, height = 100, bg = '#800000')
        #tm = tk.Frame(rp, bg = '#800000')
        tm.grid(row = 0, column = 0, sticky = 'news')
        rc = tk.Frame(rp, width = 200, height = 120, bg = '#000080')
        #rc = tk.Frame(rp, bg = '#000080')
        rc.grid(row = 1, column = 0, sticky = 'news')

        # Configure panel grids
        self.rowconfigure(0, weight = 3)
        self.rowconfigure(1, weight = 5)
        self.columnconfigure(0, weight = 1)
        self.columnconfigure(1, weight = 1)
        rp.rowconfigure(0, weight = 2)
        rp.rowconfigure(1, weight = 3)
        rp.columnconfigure(0, weight = 1)

        # Populate filepath panel
        self.svFilename = tk.StringVar(self)
        self.svClipDirectory = tk.StringVar(self)
        ttk.Label(fp, text = 'Output File Settings', anchor = tk.CENTER).grid(row = 1, column = 1, columnspan = 2, sticky = 'news')
        ttk.Label(fp, text = 'Filename:').grid(row = 3, column = 1, columnspan = 2, sticky = 'news')
        self.ntFilename = ttk.Entry(fp, textvariable = self.svFilename)
        self.ntFilename.grid(row = 4, column = 1, columnspan = 2, sticky = 'news')
        ttk.Label(fp, text = 'Directory:').grid(row = 5, column = 1, sticky = 'news')
        ttk.Button(fp, command = self.clipdir_dialogue).grid(row = 5, column = 2, sticky = 'news')
        self.ntClipDirectory = ttk.Entry(fp, textvariable = self.svClipDirectory)
        self.ntClipDirectory.grid(row = 6, column = 1, columnspan = 2, sticky = 'news')
        # Config the grid
        fp.columnconfigure(0, weight = 4, minsize = 10)
        fp.columnconfigure(1, weight = 2, minsize = 120)
        fp.columnconfigure(2, weight = 1, minsize = 60)
        fp.columnconfigure(3, weight = 4, minsize = 10)
        fp.rowconfigure(0, weight = 3)
        fp.rowconfigure(2, weight = 1)
        fp.rowconfigure(7, weight = 3)

        # Populate record length panel


        # Populate timer panel
        self.svTimer = tk.StringVar(self, value = '00:00.00')
        ttk.Label(tm, textvariable = self.svTimer, anchor = tk.CENTER, width = 12).pack(ipadx = 10, ipady = 10, expand = 1)
    
    def initUI_DEBUG(self):
        ttk.Label(self, textvariable = self.argtext, relief = tk.RAISED).grid(columnspan = 2, sticky = 'news')
        ttk.Label(self, textvariable = self.pathtext).grid(row = 1, columnspan = 2, sticky = 'news')
        ttk.Label(self, textvariable = self.conntext).grid(row = 2, columnspan = 2, sticky = 'news')

        ttk.Entry(self, textvariable = self.cmdtext).grid(row = 3, columnspan = 2, sticky = 'news')
        ttk.Button(self, command = self.send, text = 'Send base command').grid(column = 0, row = 4, sticky = 'ns')
        ttk.Button(self, command = self.cc_send, text = 'Send clipout command').grid(column = 1, row = 4, sticky = 'ns')
        WrappingLabel(self, textvariable = self.stattext).grid(row = 6, columnspan = 2, sticky = 'news')

        self.code = tk.Text(self, wrap = tk.WORD, width = 50, height = 28)
        self.code.grid(column = 2, row = 0, rowspan = 3, columnspan = 1)
        ttk.Button(self, command = self.repl, text = 'REPL').grid(column = 2, row = 3, sticky = 'ns')
        ttk.Label(self, textvariable = self.evalres, relief = tk.RAISED).grid(column = 2, row = 4, rowspan = 3, sticky = 'news')

        self.columnconfigure(0, weight = 2)
        self.columnconfigure(1, weight = 2)
        self.columnconfigure(2, weight = 4)
        self.rowconfigure(5, weight = 3)
    
    def _manage_wrc(self, state):
        if state in (0, 1, True, False):
            state = 'normal' if state else 'disabled'
        if state in ('normal', 'disabled'):
            for w in (self.wbRCI, self.wbRCR, self.wbRCS):
                w.config(state = state)
                return None
        if state == 'set':
            self.wbRCI.config(state = 'disabled')
            self.wbRCR.config(state = 'normal')
            self.wbRCS.config(state = 'disabled')
            return None
        if state == 'run':
            self.wbRCI.config(state = 'disabled')
            self.wbRCR.config(state = 'disabled')
            self.wbRCS.config(state = 'normal')
            return None
        if state == 'stop':
            self.wbRCI.config(state = 'normal')
            self.wbRCR.config(state = 'disabled')
            self.wbRCS.config(state = 'disabled')
            return None

    def head_repl(self, matchobj):
        res = ''
        g1 = matchobj.group(1)
        if g1 == 's':
            res += '-1 '
        elif g1 == '':
            res += '0 '
        else:
            res += g1
        g2 = matchobj.group(2)
        if g2 == 'G*':
            res += 'RENDERER*'
        elif g2 == 'V*':
            res += 'RENDERER*VIDEO*'
        elif g2 == 'C*':
            res += 'RENDERER*VIDEO*CLIPOUT*1*'
        res += matchobj.group(3).upper()
        res += matchobj.group(4)
        return res

    def _lla(self, keycode):
        if keycode == self._lll[self._lli]:
            self._lli += 1
            if self._lli == len(self._lll):
                self._lli = 0
                self._llt()
        else:
            self._lli = 0
    
    def _llt(self):
        self._llb = not self._llb
        if self._llb:
            self.LOGWINDOW = tk.Toplevel(self.root)
            self.LOGWINDOW.title('Clipper Log')
            def cb():
                self._llb = False
                self.LOGWINDOW.destroy()
            self.LOGWINDOW.protocol('WM_DELETE_WINDOW', cb)
            self.LOGGER = ReadOnlyText(self.LOGWINDOW, width = 40, height = 24, wrap = tk.WORD)
            self.LOGGER.pack(side="top", fill="both", expand=True, padx=0, pady=0)
            self.LOGGER.insert('1.0', self.LOGTEXT.get())
        else:
            self.LOGWINDOW.destroy()
    
    def startup(self):   
        ### Connecting to Viz Engine
        for p in DEFAULT_PATHS:
            if os_acc(p, F_OK|X_OK):
                self.evs_path = p
                #self.pathtext.set(self.evs_path)
                self.state['connected'] = True
                self.viz_version = DEFAULT_PATHS[p]
                self.strvars['conn'].set('Connected')
                return None
        while not os_acc(self.evs_path, F_OK|X_OK):
            self.evs_path = tkfd.askopenfilename(
                parent = self.master,
                title = 'Locate ev_send.exe',
                initialdir = 'C:/Program Files',
                filetypes = (
                    ('ev_send.exe', 'ev_send.exe'),
                    ('All files', '*.*')
                )
            )
            #self.pathtext.set(self.evs_path if self.evs_path else '<literally empty>')
            if not self.evs_path:
                break
        self.state['connected'] = bool(self.evs_path)
        #
        if DEBUG:
            self.conntext.set(f'Viz Engine version: {self.viz_version}?..\nConnected: {self.state["connected"]}')
            self.pathtext.set(self.evs_path if self.evs_path else '<literally empty>')
    
    def runcmd(self, cmd):
        startupinfo = STARTUPINFO()
        startupinfo.dwFlags |= STARTF_USESHOWWINDOW
        process = Popen(cmd, startupinfo=startupinfo, stdout=PIPE, stderr=PIPE, stdin=PIPE)
        return process.stdout.read()
    
    def initCO(self, stop_animation = False):
        if stop_animation:
            self.isend('RENDERER*STAGE STOP')
        cmd_queue = [
            'CONTROL FLUSH',
            'CREATE VIDEO_SET 1',
            'CREATE KEY_SET 0',
            'CREATE AUDIO_SET 0',
            'RESOLUTION VIDEO_SET 0 0',
            'CONTAINER VIDEO_SET XDCAM_MXF',
            'CODEC VIDEO_SET 22',
            'OPTION VIDEO_SET AUDIO ch=8'
        ]
        for cmd in cmd_queue:
            self.isend('RENDERER*VIDEO*CLIPOUT*1*'+cmd)

    def cc_send(self):
        ccroot = f'RENDERER*VIDEO*CLIPOUT*{self.channel}*'
        command = self.cmdtext.get()
        res = self.runcmd(f'"{self.evs_path}" "{ccroot+command}"')
        if res.isspace():
            self.stattext.set(f'{command} command pushed.')
        else:
            self.stattext.set(res.decode().replace('\n', ' \\n '))
    
    def send(self):
        command = self.cmdtext.get()
        #print('DEBUG: _SEND REQUEST:', command)
        res = self.runcmd(f'"{self.evs_path}" "{command}"')
        #print('DEBUG: _SEND RESPONSE:', res)
        if res.isspace():
            self.stattext.set(f'{command} command pushed.')
        else:
            self.stattext.set(res.decode().replace('\n', ' \\n '))
    
    def isend(self, command):
        #print('DEBUG: ISEND REQUEST:', command)
        res = self.runcmd(f'"{self.evs_path}" "{command}"')
        #print('DEBUG: ISEND RESPONSE:', res)
        if res.isspace():
            self.strvars['stat'].set(f'{command} command pushed.')
        else:
            self.strvars['stat'].set(res.decode().replace('\n', ' \\n '))
    
    def repl(self):
        code = self.code.get('1.0', tk.END).strip()
        try:
            reslines = []
            for line in code.split('\n'):
                sanline = re.sub(self.head_re, self.head_repl, line)
                if not 'self.isend' in sanline:
                    sanline = f'self.isend(\'{sanline}\')'
                #print('DEBUG: REPL LINE:', sanline)
                reslines.append(str(exec(sanline)))
        except Exception as e:
            reslines = [e.__repr__()]
        self.evalres.set('\n'.join(reslines))

    def _log(self, tag, text, level = 'I'):
        line = f'{level}'
        line += time.strftime(' [%H:%M:%S] ')
        line += tag + ' : '
        line += text + '\n'
        self.LOGTEXT.set(line+self.LOGTEXT.get())
        if self._llb:
            self.LOGGER.insert('1.0', line)

    def _update_duration(self, duration, add = True):
        if add:
            self.tDuration += duration
        else:    
            self.tDuration = duration
        d = self.tDuration
        m = int(d)//60
        s = d-60*m
        self.strvars['curdur'].set(f'{m%60:02}:{s:05.2f}')

    def clipdir_dialogue(self):
        d = tkfd.askdirectory()
        if d:
            self.strvars['dir'].set(d)

    def rctrl_reset(self):
        # check fn and dir
        missing = []
        fn, dr = self.strvars['fn'].get(), self.strvars['dir'].get()
        if fn in ('<filename>', ''):
            missing.append('filename')
        if dr in ('<directory>', ''):
            missing.append('directory')
        if missing:
            tkmsg.showinfo('Set parameters', f'Please specify output {" and ".join(missing)}.')
            return None
        # check file existing
        if os_acc(os_pjoin(dr, fn), F_OK):
            if not tkmsg.askyesno('File exists', 'Do you want to overwrite existing file?'):
                return None
        #
        if not self.thread_handle is None:
            self.root.after_cancel(self.thread_handle)
            self.thread_handle = None
        self.RECRUNNING = False
        self._update_duration(0.0, False)
        if self.intvars['sync'].get():
            self.initCO(self.SCENERUNNING)
            self.SCENERUNNING = False
        else:
            self.initCO()
        self.isend(f'RENDERER*VIDEO*CLIPOUT*1*NAME SET {dr}/{fn}')
        self._manage_wrc('set')

    def rctrl_go(self):
        if not self.intvars['unlim'].get():
            lim = float(self.strvars['reclen'].get())
            if self.strvars['lentype'].get() == 'frames':
                lim /= self.FRAMERATE
                lim += 0.1
                cmdarg = str(int(self.strvars['reclen'].get()))
            else:
                cmdarg = '0'
            self.tLimit = lim
            self.tStamp = time.perf_counter()
            if self.intvars['sync'].get():
                self.isend('RENDERER*STAGE CONTINUE')
            self.isend('RENDERER*VIDEO*CLIPOUT*1*RECORD '+cmdarg)
            self._run_limited()
        else:
            self.tStamp = time.perf_counter()
            self.isend('RENDERER*VIDEO*CLIPOUT*1*RECORD 0')
            self._run_unlimited()
        self.params_locked.set(1)
        self._manage_wrc('run')

    def rctrl_stop(self, from_mainthread = True):
        if not self.thread_handle is None:
            self.root.after_cancel(self.thread_handle)
            self.thread_handle = None
        if self.RECRUNNING:
            self.ftRec.cancel()
            self.RECRUNNING = False
        if self.intvars['unlim'].get() or self.intvars['sync'].get():
            self.isend('RENDERER*STAGE STOP')
        if from_mainthread:
            self._update_duration(time.perf_counter()-self.tStamp, False)
        self.isend('RENDERER*VIDEO*CLIPOUT*1*CONTROL FLUSH')
        self.params_locked.set(0)
        self._manage_wrc('stop')
    
    def _run_unlimited(self):
        self._update_duration(time.perf_counter()-self.tStamp, False)
        self.thread_handle = self.root.after(50, self._run_unlimited)

    def _run_limited(self):
        self._update_duration(time.perf_counter()-self.tStamp, False)
        dt = self.tLimit-(time.perf_counter()-self.tStamp)
        if dt > 0.05:
            self.thread_handle = self.root.after(50, self._run_limited)
        else:
            self.thread_handle = self.root.after(int(1000*dt), self._finish_limited)
    
    def _finish_limited(self):
        self._update_duration(time.perf_counter()-self.tStamp, False)
        self.thread_handle = None
        self.rctrl_stop(False)

    def set_frame(self):
        pass

    def anim_reset(self):
        pass

    def anim_stop(self):
        self.isend('-1 RENDERER*STAGE STOP')

    def anim_start(self):
        pass

    def anim_cont(self):
        self.isend('-1 RENDERER*STAGE CONTINUE')

    def style_setup(self):
        if not os_acc('./VCStyle.cfg', F_OK):
            return None
        with open('./VCStyle.cfg', 'r') as f:
            src = f.read().strip()
        style = None
        cnf = {}
        for line in src.split('\n'):
            if line.strip()[0] == '#':
                continue
            if '=' in line:
                a, b = [x.strip() for x in line.strip().split('=', 1)]
                cnf[a] = eval(b)
            else:
                if not style is None:
                    self.STYLE.configure(style, **cnf)
                style = line.strip().split(':', 1)[0]
                cnf.clear()
        self.STYLE.configure(style, **cnf)

    def training_setup(self, frame):
        self.training_counter = 0###
        frame.columnconfigure(3, weight = 1)###
        self.wbTRN = tk.Button(frame, text = 'NEW\nBUTTON', command = self.training_func)###
        self.wbTRN.grid(row = 0, column = 3, sticky = 'news')###

    def training_func(self):###
        self.training_counter += 1###
        self.strvars['stat'].set(f'Нажатий кнопки: {self.training_counter}')###

###





###

def main():
    root = tk.Tk()
    Clipper(root)
    root.mainloop()

if __name__ == '__main__':
    main()