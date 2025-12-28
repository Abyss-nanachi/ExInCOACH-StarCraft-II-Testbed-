using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Security.Permissions;
using Microsoft.Win32;
using System.Net;
using System.Threading;

namespace SC2Overlay
{
    public class OverlayApp : ApplicationContext
    {
        private OverlayForm _overlay;
        private ChatForm _chat;

        public OverlayApp()
        {
            try 
            {
                _overlay = new OverlayForm();
                _overlay.Show();
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error initializing Overlay: " + ex.Message);
            }

            try
            {
                _chat = new ChatForm(_overlay);
                _chat.Show();
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error initializing Chat: " + ex.Message);
            }

            if (_chat != null) _chat.FormClosed += OnFormClosed;
            if (_overlay != null) _overlay.FormClosed += OnFormClosed;
        }

        private void OnFormClosed(object sender, FormClosedEventArgs e)
        {
            if (sender is ChatForm) ExitThread();
        }
    }

    public class OverlayForm : Form
    {
        // P/Invoke
        [DllImport("user32.dll", SetLastError = true)]
        static extern int GetWindowLong(IntPtr hWnd, int nIndex);
        [DllImport("user32.dll")]
        static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
        [DllImport("user32.dll")]
        static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
        
        [DllImport("user32.dll")]
        static extern bool GetClientRect(IntPtr hWnd, out RECT lpRect);
        
        [DllImport("user32.dll")]
        static extern bool ClientToScreen(IntPtr hWnd, ref POINT lpPoint);

        [DllImport("user32.dll")]
        static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
        
        [StructLayout(LayoutKind.Sequential)]
        public struct POINT { public int X; public int Y; }

        static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
        const uint SWP_NOACTIVATE = 0x0010;
        const uint SWP_SHOWWINDOW = 0x0040;

        private System.Windows.Forms.Timer _timer;
        private string _dataFile = "overlay_data.json";
        private string _configFile = "config.json";
        private string _mappingFile = "action_mapping.json";
        private JavaScriptSerializer _serializer = new JavaScriptSerializer();
        private OverlayData _data = new OverlayData();
        private Dictionary<string, Dictionary<string, object>> _actionMap = new Dictionary<string, Dictionary<string, object>>();
        private DateTime _lastMod = DateTime.MinValue;

        public OverlayConfig Config = new OverlayConfig();
        public RootConfig GlobalConfig = new RootConfig();
        public bool IsCalibrating = false;
        
        private string _currentLang = "zh"; // Default to Chinese

        [DllImport("kernel32.dll")]
        static extern bool AllocConsole();

        public OverlayForm()
        {
            AllocConsole(); // Create a console window for debugging output
            this.FormBorderStyle = FormBorderStyle.None;
            this.ShowInTaskbar = false;
            this.TopMost = true;
            this.BackColor = Color.Magenta;
            this.TransparencyKey = Color.Magenta;
            this.DoubleBuffered = true;
            this.StartPosition = FormStartPosition.Manual;
            this.Location = new Point(0, 0);
            this.Size = new Size(100, 100);

            // Click-through configuration
            // WS_EX_LAYERED (0x80000) is required for TransparencyKey
            // WS_EX_TRANSPARENT (0x20) makes the window click-through (ignore mouse events)
            // Since we moved the interactive controls to ChatForm, we can make OverlayForm fully click-through again!
            int initialStyle = GetWindowLong(this.Handle, -20); // GWL_EXSTYLE
            SetWindowLong(this.Handle, -20, initialStyle | 0x80000 | 0x20); // Added | 0x20 for click-through
            
            LoadConfig();
            LoadActionMapping();
            
            _timer = new System.Windows.Forms.Timer();
            _timer.Interval = 50; // Faster updates for tracking (20fps)
            _timer.Tick += UpdateOverlay;
            _timer.Start();
        }

        public void SetLanguage(string lang)
        {
            _currentLang = lang;
            this.Invalidate();
        }

        public void LoadActionMapping()
        {
            try
            {
                if (File.Exists(_mappingFile))
                {
                    string json = File.ReadAllText(_mappingFile, Encoding.UTF8);
                    _actionMap = _serializer.Deserialize<Dictionary<string, Dictionary<string, object>>>(json);
                    Console.WriteLine("Action Mapping Loaded: " + _actionMap.Count + " entries.");
                }
                else
                {
                    Console.WriteLine("Action Mapping file not found: " + _mappingFile);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error loading action mapping: " + ex.Message);
            }
        }

        public void LoadConfig()
        {
            try
            {
                if (File.Exists(_configFile))
                {
                    string json = File.ReadAllText(_configFile);
                    GlobalConfig = _serializer.Deserialize<RootConfig>(json);
                    if (GlobalConfig != null && GlobalConfig.overlay != null)
                    {
                        Config = GlobalConfig.overlay;
                    }
                    else
                    {
                        Console.WriteLine("Config loaded but overlay section is missing.");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error loading config: " + ex.Message);
            }
        }

        public void SaveConfig()
        {
            try
            {
                // Update GlobalConfig's overlay with current Config
                GlobalConfig.overlay = Config;
                
                string json = _serializer.Serialize(GlobalConfig);
                File.WriteAllText(_configFile, json);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error saving config: " + ex.Message);
            }
        }

        [DllImport("user32.dll")]
        static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        private IntPtr FindSC2Window()
        {
            // 1. Try FindWindow by ClassName (usually "StarCraft II")
            IntPtr hwnd = FindWindow("StarCraft II", null);
            if (hwnd != IntPtr.Zero) return hwnd;

            // 2. Try FindWindow by WindowName
            hwnd = FindWindow(null, "StarCraft II");
            if (hwnd != IntPtr.Zero) return hwnd;

            // 3. Robust: Find by Process Name
            System.Diagnostics.Process[] processes = System.Diagnostics.Process.GetProcessesByName("SC2_x64");
            if (processes.Length > 0) return processes[0].MainWindowHandle;
            
            processes = System.Diagnostics.Process.GetProcessesByName("SC2");
            if (processes.Length > 0) return processes[0].MainWindowHandle;

            return IntPtr.Zero;
        }

        private void UpdateOverlay(object sender, EventArgs e)
        {
            // Track SC2 Window
            IntPtr sc2Wnd = FindSC2Window();
            // Console.WriteLine("FindSC2Window result: " + sc2Wnd); 

            if (sc2Wnd != IntPtr.Zero)
            {
                RECT clientRect;
                bool getRectSuccess = GetClientRect(sc2Wnd, out clientRect);
                
                POINT topLeft = new POINT { X = 0, Y = 0 };
                bool clientToScreenSuccess = ClientToScreen(sc2Wnd, ref topLeft);
                
                int w = clientRect.Right - clientRect.Left;
                int h = clientRect.Bottom - clientRect.Top;

                // Log window tracking occasionally or on change
                // Console.WriteLine(string.Format("Window Track: RectSuccess={0}, ToScreenSuccess={1}, Size={2}x{3} @ {4},{5}", 
                //    getRectSuccess, clientToScreenSuccess, w, h, topLeft.X, topLeft.Y));

                // Robust positioning using SetWindowPos
                // Only update if dimensions or position changed significantly to avoid jitter
                if (w > 0 && h > 0)
                {
                    // Check if update is needed
                    if (Math.Abs(this.Left - topLeft.X) > 2 || 
                        Math.Abs(this.Top - topLeft.Y) > 2 ||
                        Math.Abs(this.Width - w) > 2 ||
                        Math.Abs(this.Height - h) > 2)
                    {
                        Console.WriteLine(string.Format("Updating Overlay Pos: {0},{1} {2}x{3}", topLeft.X, topLeft.Y, w, h));
                        SetWindowPos(this.Handle, HWND_TOPMOST, topLeft.X, topLeft.Y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW);
                    }
                }
            }
            else
            {
                // Console.WriteLine("StarCraft II window not found.");
            }

            // Read Data
            try
            {
                if (File.Exists(_dataFile))
                {
                    DateTime mod = File.GetLastWriteTime(_dataFile);
                    if (mod > _lastMod)
                    {
                        _lastMod = mod;
                        string json = "";
                        for(int i=0; i<3; i++) { 
                            try { json = File.ReadAllText(_dataFile); break; } 
                            catch { Thread.Sleep(5); } 
                        }
                        
                        if (!string.IsNullOrEmpty(json))
                        {
                            try {
                                _data = _serializer.Deserialize<OverlayData>(json);
                                
                                // Debug: Check Cues
                                if (_data != null) {
                                    int count = _data.cues != null ? _data.cues.Count : 0;
                                    Console.WriteLine(string.Format("Data Loaded. Cues: {0}. Decision: {1}", count, _data.decision));
                                    if (count > 0) {
                                        foreach(var c in _data.cues) {
                                            Console.WriteLine(string.Format("  Cue: Type={0}, Coord={1}, Text={2}", c.type, c.coordinate, c.text));
                                        }
                                    }
                                    
                                    // Log to file
                                    LogData(_data);
                                } else {
                                    Console.WriteLine("Data deserialized to null.");
                                }
                                
                                this.Invalidate(); 
                            }
                            catch (Exception ex) {
                                Console.WriteLine("JSON Parse Error: " + ex.Message);
                            }
                        }
                    }
                }
            }
            catch (Exception ex) {
                Console.WriteLine("File Read Error: " + ex.Message);
            }
        }
        
        private void LogData(OverlayData data)
        {
            try
            {
                string logFile = "overlay_log.txt";
                using (StreamWriter sw = File.AppendText(logFile))
                {
                    string timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
                    sw.WriteLine(string.Format("[{0}] Decision: {1}", timestamp, data.decision));
                    
                    if (data.debug != null)
                    {
                         JavaScriptSerializer serializer = new JavaScriptSerializer();
                         string debugJson = serializer.Serialize(data.debug);
                         sw.WriteLine("    Debug: " + debugJson);
                    }

                    if (data.cues != null && data.cues.Count > 0)
                    {
                        foreach (var cue in data.cues)
                        {
                            sw.WriteLine(string.Format("    Cue: Type={0}, Text={1}, Pos={2},{3}", 
                                cue.type, cue.text, 
                                (cue.pos != null && cue.pos.Length > 0) ? cue.pos[0] : -1,
                                (cue.pos != null && cue.pos.Length > 1) ? cue.pos[1] : -1));
                        }
                    }
                    sw.WriteLine("--------------------------------------------------");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Log Error: " + ex.Message);
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;

            // --- Debug: Draw Border to verify Window Tracking ---
            using (Pen borderPen = new Pen(Color.Lime, 4))
            {
                // Draw inside the bounds
                g.DrawRectangle(borderPen, 2, 2, this.Width - 4, this.Height - 4);
            }

            // --- Calibration Mode ---
            if (IsCalibrating)
            {
                float x1 = ScaleMinimapX(0);
                float y1 = ScaleMinimapY(0); // Top-Left
                float x2 = ScaleMinimapX(64);
                float y2 = ScaleMinimapY(64); // Bottom-Right

                using (Pen p = new Pen(Color.Magenta, 4))
                {
                    g.DrawRectangle(p, x1, y1, x2 - x1, y2 - y1);
                }
                
                using (Font f = new Font("Arial", 14, FontStyle.Bold))
                {
                    g.DrawString("Minimap Calibration Mode", f, Brushes.Magenta, x1, y1 - 30);
                }
            }

            // Draw Decision/Recommendation Text
            if (_data != null && !string.IsNullOrEmpty(_data.decision))
            {
                using (Font font = new Font("Segoe UI", 16, FontStyle.Bold))
                using (Brush bgBrush = new SolidBrush(Color.FromArgb(180, 0, 0, 0)))
                using (Brush textBrush = new SolidBrush(Color.Yellow))
                {
                    string text = "Recommended: " + GetLocalizedText(_data.decision);
                    SizeF size = g.MeasureString(text, font);
                    // Draw at top center
                    float x = (this.Width - size.Width) / 2;
                    float y = 50; 
                    
                    g.FillRectangle(bgBrush, x - 10, y - 5, size.Width + 20, size.Height + 10);
                    g.DrawString(text, font, textBrush, x, y);
                }
            }

            if (_data == null || _data.cues == null) return;

            foreach (var cue in _data.cues)
            {
                DrawCue(g, cue);
            }
        }

        private float ScaleX(int x, string coordSys) 
        { 
            if (coordSys == "minimap") return ScaleMinimapX(x);
            return x / 64.0f * this.Width; 
        }
        
        private float ScaleY(int y, string coordSys) 
        { 
            if (coordSys == "minimap") return ScaleMinimapY(y);
            return y / 64.0f * this.Height; 
        }

        // Configurable Minimap location
        private float ScaleMinimapX(int x)
        {
            float minimapSize = this.Height * Config.MinimapScale;
            float offsetX = this.Width * Config.MinimapOffsetX;
            return offsetX + (x / 64.0f * minimapSize);
        }

        private float ScaleMinimapY(int y)
        {
            float minimapSize = this.Height * Config.MinimapScale;
            float baseY = this.Height - minimapSize;
            float offsetY = this.Height * Config.MinimapOffsetY;
            return baseY + offsetY + (y / 64.0f * minimapSize);
        }

        private string GetLocalizedText(string rawText)
        {
            if (_currentLang == "raw") return rawText;
            if (string.IsNullOrEmpty(rawText)) return "";
            if (_actionMap == null || _actionMap.Count == 0) return rawText;

            // Try exact match first
            // visual_cues.py currently sends "Clean Name" (e.g. "Build Marine").
            // But our mapping has both raw ("Build_Marine_quick") and clean keys ("Build Marine").
            // So it should work directly.
            
            if (_actionMap.ContainsKey(rawText))
            {
                var entry = _actionMap[rawText];
                if (entry.ContainsKey(_currentLang))
                {
                    return entry[_currentLang].ToString();
                }
            }
            
            // Log missing mapping if not raw
            // Avoid spamming log? Maybe only once per session per key?
            // For now, simple console output
            // Console.WriteLine("Missing mapping for: " + rawText);
            
            return rawText;
        }

        private void DrawCue(Graphics g, Cue cue)
        {
            Color c = Color.Red;
            if (!string.IsNullOrEmpty(cue.color))
            {
                try { c = ColorTranslator.FromHtml(cue.color); } catch { c = Color.Red; }
            }
            
            // Localize Text
            string displayText = GetLocalizedText(cue.text);

            // Colors for stroke and fill
            // FIX: TransparencyKey does not support partial alpha blending well on Windows Forms.
            // Any semi-transparent pixel blended with the Black background becomes a dark non-black pixel,
            // which is NOT transparent and blocks the game view.
            // Solution: Do NOT fill rectangles. Only draw outlines.
            Color strokeC = Color.FromArgb(255, c); // Full opacity for stroke
            Color fillC = Color.FromArgb(0, c); // No fill

            using (Pen p = new Pen(strokeC, 3))
            using (Brush b = new SolidBrush(strokeC))
            using (Brush fillB = new SolidBrush(fillC))
            {
                // Safety checks for arrays
                bool hasStart = cue.start != null && cue.start.Length >= 2;
                bool hasEnd = cue.end != null && cue.end.Length >= 2;
                bool hasCenter = cue.center != null && cue.center.Length >= 2;
                bool hasPos = cue.pos != null && cue.pos.Length >= 2;

                if (cue.type == "arrow" && hasStart && hasEnd)
                {
                    p.CustomEndCap = new System.Drawing.Drawing2D.AdjustableArrowCap(5, 5);
                    g.DrawLine(p, 
                        ScaleX(cue.start[0], cue.coordinate), ScaleY(cue.start[1], cue.coordinate), 
                        ScaleX(cue.end[0], cue.coordinate), ScaleY(cue.end[1], cue.coordinate));
                    
                    // Optional: Draw text at start or end? Usually not for arrow unless specified.
                }
                else if (cue.type == "box" && hasStart && hasEnd)
                {
                    float x1 = ScaleX(cue.start[0], cue.coordinate);
                    float y1 = ScaleY(cue.start[1], cue.coordinate);
                    float x2 = ScaleX(cue.end[0], cue.coordinate);
                    float y2 = ScaleY(cue.end[1], cue.coordinate);
                    
                    // Normalize coordinates for DrawRectangle
                    float x = Math.Min(x1, x2);
                    float y = Math.Min(y1, y2);
                    float w = Math.Abs(x2 - x1);
                    float h = Math.Abs(y2 - y1);
                    
                    // Fill and Outline
                    // g.FillRectangle(fillB, x, y, w, h); // Disabled to prevent blocking view
                    g.DrawRectangle(p, x, y, w, h);
                    
                    if (!string.IsNullOrEmpty(displayText))
                        DrawTextWithBackground(g, displayText, x, y - 25, strokeC);
                }
                else if (cue.type == "ripple" && (hasStart || hasPos))
                {
                    float cx, cy;
                    if (hasStart) {
                        cx = ScaleX(cue.start[0], cue.coordinate);
                        cy = ScaleY(cue.start[1], cue.coordinate);
                    } else {
                        cx = ScaleX(cue.pos[0], cue.coordinate);
                        cy = ScaleY(cue.pos[1], cue.coordinate);
                    }

                    float r = cue.radius > 0 ? cue.radius : 20;
                    
                    // Draw 3 concentric circles with thinner lines
                    using (Pen thinPen = new Pen(strokeC, 1.5f))
                    {
                        g.DrawEllipse(thinPen, cx - r, cy - r, r * 2, r * 2);
                        g.DrawEllipse(thinPen, cx - r*0.7f, cy - r*0.7f, r * 1.4f, r * 1.4f);
                        g.DrawEllipse(thinPen, cx - r*0.4f, cy - r*0.4f, r * 0.8f, r * 0.8f);
                    }
                    
                    if (!string.IsNullOrEmpty(displayText))
                        DrawTextWithBackground(g, displayText, cx, cy - r - 25, strokeC);
                }
                else if (cue.type == "circle" && hasCenter)
                {
                    float cx = ScaleX(cue.center[0], cue.coordinate);
                    float cy = ScaleY(cue.center[1], cue.coordinate);
                    float r = cue.radius > 0 ? cue.radius : 10;
                    
                    g.DrawEllipse(p, cx - r, cy - r, r * 2, r * 2);
                    
                    if (!string.IsNullOrEmpty(displayText))
                        DrawTextWithBackground(g, displayText, cx, cy - r - 25, strokeC);
                }
                else if (cue.type == "text" && hasPos)
                {
                    DrawTextWithBackground(g, displayText, ScaleX(cue.pos[0], cue.coordinate), ScaleY(cue.pos[1], cue.coordinate), strokeC);
                }
                else if (cue.type == "crosshair" && hasPos)
                {
                    float cx = ScaleX(cue.pos[0], cue.coordinate);
                    float cy = ScaleY(cue.pos[1], cue.coordinate);
                    float r = 10;
                    
                    g.DrawLine(p, cx - r, cy, cx + r, cy);
                    g.DrawLine(p, cx, cy - r, cx, cy + r);
                    
                    if (!string.IsNullOrEmpty(displayText))
                        DrawTextWithBackground(g, displayText, cx + 5, cy - 25, strokeC);
                }
            }
        }

        private void DrawTextWithBackground(Graphics g, string text, float x, float y, Color textColor)
        {
            if (string.IsNullOrEmpty(text)) return;
            
            using (Font f = new Font("Segoe UI", 12, FontStyle.Bold))
            using (Brush bg = new SolidBrush(Color.FromArgb(160, 0, 0, 0)))
            using (Brush tb = new SolidBrush(textColor))
            {
                SizeF size = g.MeasureString(text, f);
                // Draw background
                g.FillRectangle(bg, x, y, size.Width + 4, size.Height + 4);
                // Draw text
                g.DrawString(text, f, tb, x + 2, y + 2);
            }
        }
    }

    // --- Chat Form with WebBrowser ---
    [PermissionSet(SecurityAction.Demand, Name = "FullTrust")]
    [ComVisible(true)]
    public class ChatForm : Form
    {
        private WebBrowser _browser;
        private TextBox _inputBox;
        private System.Windows.Forms.Timer _chatTimer;
        private string _dataFile = "overlay_data.json";
        private DateTime _lastModified = DateTime.MinValue;
        private JavaScriptSerializer _serializer = new JavaScriptSerializer();
        private OverlayData _currentData = new OverlayData();
        private OverlayForm _overlay;

        public ChatForm(OverlayForm overlay)
        {
            _overlay = overlay;
            this.Text = "ExInCOACH Chat";
            this.Size = new Size(400, 600);
            this.StartPosition = FormStartPosition.Manual;
            this.Location = new Point(Screen.PrimaryScreen.WorkingArea.Width - 420, 100);
            this.TopMost = true;
            this.BackColor = Color.FromArgb(10, 17, 40); 
            
            _browser = new WebBrowser();
            _browser.Dock = DockStyle.Fill;
            _browser.IsWebBrowserContextMenuEnabled = false;
            _browser.WebBrowserShortcutsEnabled = false;
            _browser.ObjectForScripting = this;
            _browser.ScriptErrorsSuppressed = true;
            this.Controls.Add(_browser);

            string htmlPath = Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "chat_legacy.html");
            if (File.Exists(htmlPath))
            {
                _browser.Navigate(new Uri(htmlPath));
            }
            else
            {
                _browser.DocumentText = "<html><body style='background:#000;color:white;'>Chat HTML not found!</body></html>";
            }

            // --- Top Panel for Settings ---
            Panel topPanel = new Panel();
            topPanel.Dock = DockStyle.Top;
            topPanel.Height = 40;
            topPanel.BackColor = Color.FromArgb(20, 30, 60);
            topPanel.Padding = new Padding(5);
            
            FlowLayoutPanel rightHeader = new FlowLayoutPanel();
            rightHeader.Dock = DockStyle.Right;
            rightHeader.AutoSize = true;
            rightHeader.FlowDirection = FlowDirection.LeftToRight;
            rightHeader.WrapContents = false;
            
            // Language Combo
            ComboBox langCombo = new ComboBox();
            langCombo.Items.AddRange(new string[] { "Raw", "中文", "English" });
            langCombo.SelectedIndex = 1; // Default to Chinese
            langCombo.DropDownStyle = ComboBoxStyle.DropDownList;
            langCombo.Width = 80;
            langCombo.FlatStyle = FlatStyle.Flat;
            langCombo.Font = new Font("Segoe UI", 9, FontStyle.Bold);
            langCombo.SelectedIndexChanged += (s, e) => {
                string lang = "zh";
                switch (langCombo.SelectedIndex)
                {
                    case 0: lang = "raw"; break;
                    case 1: lang = "zh"; break;
                    case 2: lang = "en"; break;
                }
                _overlay.SetLanguage(lang);
            };
            
            // Adjust Map Button
            Button adjustBtn = new Button();
            adjustBtn.Text = "Adjust Map";
            adjustBtn.Width = 90;
            adjustBtn.FlatStyle = FlatStyle.Flat;
            adjustBtn.FlatAppearance.BorderSize = 0;
            adjustBtn.BackColor = Color.FromArgb(50, 50, 50);
            adjustBtn.ForeColor = Color.White;
            adjustBtn.Font = new Font("Segoe UI", 9);
            adjustBtn.Margin = new Padding(5, 0, 0, 0);
            adjustBtn.Click += AdjustBtn_Click;
            
            rightHeader.Controls.Add(langCombo);
            rightHeader.Controls.Add(adjustBtn);
            topPanel.Controls.Add(rightHeader);
            
            this.Controls.Add(topPanel);

            // --- Input Panel ---
            Panel inputPanel = new Panel();
            inputPanel.Dock = DockStyle.Bottom;
            inputPanel.Height = 40;
            inputPanel.BackColor = Color.FromArgb(0, 168, 255);
            inputPanel.Padding = new Padding(2);

            Button sendBtn = new Button();
            sendBtn.Text = "Send";
            sendBtn.Dock = DockStyle.Right;
            sendBtn.Width = 70;
            sendBtn.FlatStyle = FlatStyle.Flat;
            sendBtn.FlatAppearance.BorderSize = 0;
            sendBtn.BackColor = Color.FromArgb(0, 130, 200);
            sendBtn.ForeColor = Color.White;
            sendBtn.Font = new Font("Segoe UI", 9, FontStyle.Bold);
            sendBtn.Cursor = Cursors.Hand;
            sendBtn.Click += SendBtn_Click;
            inputPanel.Controls.Add(sendBtn);
            
            _inputBox = new TextBox();
            _inputBox.Dock = DockStyle.Fill;
            _inputBox.Font = new Font("Segoe UI", 14);
            _inputBox.BorderStyle = BorderStyle.None;
            _inputBox.KeyDown += InputBox_KeyDown;
            inputPanel.Controls.Add(_inputBox);
            
            this.Controls.Add(inputPanel);

            _chatTimer = new System.Windows.Forms.Timer { Interval = 500 };
            _chatTimer.Tick += ChatTimer_Tick;
            _chatTimer.Start();
            
            System.Windows.Forms.Timer initTimer = new System.Windows.Forms.Timer { Interval = 1000 };
            initTimer.Tick += (s, e) => {
                AppendSystemMessage("Hello, I am your SC2 ExInCoach. Ask me anything about the current game!");
                initTimer.Stop();
            };
            initTimer.Start();
        }

        private void AdjustBtn_Click(object sender, EventArgs e)
        {
            MinimapAdjustForm adjustForm = new MinimapAdjustForm(_overlay);
            adjustForm.Show();
        }

        private void InputBox_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                SendMessage();
                e.SuppressKeyPress = true;
            }
        }

        private void SendBtn_Click(object sender, EventArgs e)
        {
            SendMessage();
        }

        private void SendMessage()
        {
            string msg = _inputBox.Text.Trim();
            if (!string.IsNullOrEmpty(msg))
            {
                AppendUserMessage(msg);
                _inputBox.Clear();
                
                string observation = (_currentData != null) ? _currentData.observation : "";
                var config = _overlay.GlobalConfig.chat_llm;
                
                if (config != null && !string.IsNullOrEmpty(config.api_key))
                {
                    Thread t = new Thread(() => CallLLM(msg, observation, config));
                    t.IsBackground = true;
                    t.Start();
                }
                else
                {
                    AppendSystemMessage("Error: Chat LLM Config not found in config.json.");
                }
            }
            _inputBox.Focus();
        }

        private void CallLLM(string userMsg, string observation, LLMConfig config)
        {
            try
            {
                this.Invoke((MethodInvoker)delegate {
                    AppendSystemMessage("Thinking...");
                });
                
                string url = config.api_base.TrimEnd('/') + "/chat/completions";
                var request = (HttpWebRequest)WebRequest.Create(url);
                request.Method = "POST";
                request.ContentType = "application/json";
                request.Headers.Add("Authorization", "Bearer " + config.api_key);

                string systemPrompt = "You are an expert StarCraft II coach. Answer questions based on the game observation. Keep answers concise and helpful.";
                string content = string.Format("Observation:\n{0}\n\nUser Question: {1}", observation, userMsg);
                
                string model = !string.IsNullOrEmpty(config.model_name) ? config.model_name : "gpt-3.5-turbo";
                
                string jsonPayload = string.Format(
                    "{{\"model\": \"{0}\", \"messages\": [{{\"role\": \"system\", \"content\": \"{1}\"}}, {{\"role\": \"user\", \"content\": \"{2}\"}}], \"stream\": false}}",
                    model,
                    EscapeJson(systemPrompt),
                    EscapeJson(content)
                );

                using (var streamWriter = new StreamWriter(request.GetRequestStream()))
                {
                    streamWriter.Write(jsonPayload);
                }

                var httpResponse = (HttpWebResponse)request.GetResponse();
                using (var streamReader = new StreamReader(httpResponse.GetResponseStream()))
                {
                    var result = streamReader.ReadToEnd();
                    var responseObj = _serializer.Deserialize<OpenAIResponse>(result);
                    string answer = "";
                    if (responseObj != null && responseObj.choices != null && responseObj.choices.Length > 0)
                        answer = responseObj.choices[0].message.content;
                    else
                        answer = "No response from LLM.";
                    
                    this.Invoke((MethodInvoker)delegate {
                        UpdateLastSystemMessage(answer);
                    });
                }
            }
            catch (Exception ex)
            {
                this.Invoke((MethodInvoker)delegate {
                    UpdateLastSystemMessage("Error calling LLM: " + ex.Message);
                });
            }
        }

        private string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "");
        }

        private void ChatTimer_Tick(object sender, EventArgs e)
        {
            try
            {
                if (File.Exists(_dataFile))
                {
                    DateTime writeTime = File.GetLastWriteTime(_dataFile);
                    if (writeTime > _lastModified)
                    {
                        _lastModified = writeTime;
                        string json = "";
                        for (int i=0; i<3; i++) {
                            try { json = File.ReadAllText(_dataFile); break; }
                            catch { System.Threading.Thread.Sleep(10); }
                        }
                        
                        if (!string.IsNullOrEmpty(json))
                        {
                            _currentData = _serializer.Deserialize<OverlayData>(json);
                        }
                    }
                }
            }
            catch { }
        }

        private void UpdateLastSystemMessage(string text)
        {
            if (_browser.Document != null)
            {
                _browser.Document.InvokeScript("updateLastMessage", new object[] { text });
            }
        }

        private void AppendSystemMessage(string text)
        {
            if (_browser.Document != null)
            {
                _browser.Document.InvokeScript("addMessage", new object[] { "system", text });
            }
        }

        private void AppendUserMessage(string text)
        {
             if (_browser.Document != null)
            {
                _browser.Document.InvokeScript("addMessage", new object[] { "user", text });
            }
        }
    }

    // --- Minimap Adjustment Form ---
    public class MinimapAdjustForm : Form
    {
        private OverlayForm _overlay;
        
        public MinimapAdjustForm(OverlayForm overlay)
        {
            _overlay = overlay;
            _overlay.IsCalibrating = true;
            _overlay.Invalidate();

            this.Text = "Adjust Minimap";
            this.Size = new Size(250, 300);
            this.TopMost = true;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedToolWindow;
            this.FormClosed += (s, e) => {
                _overlay.IsCalibrating = false;
                _overlay.Invalidate();
            };

            FlowLayoutPanel panel = new FlowLayoutPanel();
            panel.Dock = DockStyle.Fill;
            panel.FlowDirection = FlowDirection.TopDown;
            panel.Padding = new Padding(10);
            this.Controls.Add(panel);

            // Scale
            panel.Controls.Add(new Label { Text = "Scale (Size)", AutoSize = true });
            AddControls(panel, "-", "+", (d) => {
                _overlay.Config.MinimapScale += d * 0.01f;
                if(_overlay.Config.MinimapScale < 0.05f) _overlay.Config.MinimapScale = 0.05f;
            });

            // Offset X
            panel.Controls.Add(new Label { Text = "Offset X (Horizontal)", AutoSize = true });
            AddControls(panel, "Left", "Right", (d) => {
                _overlay.Config.MinimapOffsetX += d * 0.005f;
            });

            // Offset Y
            panel.Controls.Add(new Label { Text = "Offset Y (Vertical)", AutoSize = true });
            AddControls(panel, "Up", "Down", (d) => {
                _overlay.Config.MinimapOffsetY += d * 0.005f;
            });

            // Save Button
            Button saveBtn = new Button { Text = "Save & Close", Width = 200, Height = 40, BackColor = Color.LightGreen };
            saveBtn.Click += (s, e) => {
                _overlay.SaveConfig();
                this.Close();
            };
            panel.Controls.Add(saveBtn);
        }

        private void AddControls(Panel p, string labelMinus, string labelPlus, Action<float> action)
        {
            FlowLayoutPanel row = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
            
            Button btnMinus = new Button { Text = labelMinus, Width = 60 };
            btnMinus.Click += (s, e) => { action(-1f); _overlay.Invalidate(); };
            
            Button btnPlus = new Button { Text = labelPlus, Width = 60 };
            btnPlus.Click += (s, e) => { action(1f); _overlay.Invalidate(); };

            row.Controls.Add(btnMinus);
            row.Controls.Add(btnPlus);
            p.Controls.Add(row);
        }
    }

    // --- Data Classes ---
    public class OverlayData
    {
        public List<Cue> cues { get; set; }
        public string observation { get; set; }
        public string decision { get; set; }
        public LLMConfig llm_config { get; set; }
        public object debug { get; set; }
    }

    public class RootConfig
    {
        public LLMConfig decision_llm { get; set; }
        public LLMConfig decision_vlm { get; set; }
        public LLMConfig chat_llm { get; set; }
        public OverlayConfig overlay { get; set; }
        
        public RootConfig()
        {
            decision_llm = new LLMConfig();
            decision_vlm = new LLMConfig();
            chat_llm = new LLMConfig();
            overlay = new OverlayConfig();
        }
    }

    public class OverlayConfig
    {
        public float MinimapScale { get; set; }
        public float MinimapOffsetX { get; set; }
        public float MinimapOffsetY { get; set; }

        public OverlayConfig()
        {
            MinimapScale = 0.22f;
            MinimapOffsetX = 0.0f;
            MinimapOffsetY = 0.0f;
        }
    }

    public class LLMConfig
    {
        public string api_key { get; set; }
        public string api_base { get; set; }
        public string model_name { get; set; }
        public float temperature { get; set; }
    }

    public class OpenAIResponse
    {
        public Choice[] choices { get; set; }
    }

    public class Choice
    {
        public Message message { get; set; }
    }

    public class Message
    {
        public string content { get; set; }
    }
    
    public class Cue
    {
        public string type { get; set; }
        public string coordinate { get; set; }
        public int[] start { get; set; }
        public int[] end { get; set; }
        public int[] center { get; set; }
        public int[] pos { get; set; }
        public string color { get; set; }
        public string text { get; set; }
        public float radius { get; set; }
    }

    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new OverlayApp());
        }
    }
}
