using System.Diagnostics;
using System.Drawing.Imaging;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Xml.Linq;
using Microsoft.Win32;

namespace FusionMyFreeCAD.Setup;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 4 && args[0] == "--merge-ribbon")
        {
            try
            {
                RibbonMerger.Merge(args[1], args[2], args[3]);
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.Message);
                return 1;
            }
        }
        if (args.Length == 2 && args[0] == "--verify-ribbon")
        {
            try { return RibbonMerger.Verify(args[1]) ? 0 : 2; }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        if (args.Length >= 2 && args[0] == "--discover-freecad")
        {
            try
            {
                var projectRoot = args.Length >= 3 ? args[2] : AppContext.BaseDirectory;
                var settings = LauncherSettings.Load();
                var installations = FreeCadDiscovery.Discover(projectRoot, settings.CustomExecutables);
                File.WriteAllText(args[1], JsonSerializer.Serialize(installations, new JsonSerializerOptions { WriteIndented = true }));
                return 0;
            }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        if (args.Length == 1 && args[0] == "--smoke-ui")
        {
            try
            {
                ApplicationConfiguration.Initialize();
                using var form = new SetupForm();
                form.CreateControl();
                return form.Controls.Find("MainTabs", true).Length == 1
                    && form.Controls.Find("InstallationsList", true).Length == 1
                    && form.Controls.Find("InstallButton", true).Length == 1 ? 0 : 2;
            }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        if (args.Length == 2 && args[0] == "--inspect-ui")
        {
            try
            {
                ApplicationConfiguration.Initialize();
                using var form = new SetupForm();
                form.Show();
                Application.DoEvents();
                var tabs = (TabControl)form.Controls.Find("MainTabs", true).Single();
                var list = (ListView)form.Controls.Find("InstallationsList", true).Single();
                var launch = (Button)form.Controls.Find("LaunchButton", true).Single();
                var install = (Button)form.Controls.Find("InstallButton", true).Single();
                File.WriteAllText(args[1], JsonSerializer.Serialize(new
                {
                    ProjectRoot = form.ProjectRoot,
                    PackageVersion = form.PackageVersion,
                    FormClientSize = form.ClientSize,
                    TabsBounds = tabs.Bounds,
                    ListBounds = list.Bounds,
                    LaunchButtonBounds = launch.Bounds,
                    LaunchButtonVisible = launch.Visible,
                    InstallButtonText = install.Text,
                    ItemCount = list.Items.Count,
                    Items = list.Items.Cast<ListViewItem>().Select(item => item.SubItems.Cast<ListViewItem.ListViewSubItem>().Select(value => value.Text).ToArray()).ToArray()
                }, new JsonSerializerOptions { WriteIndented = true }));
                return 0;
            }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        if (args.Length == 2 && args[0] == "--screenshot-ui")
        {
            try
            {
                ApplicationConfiguration.Initialize();
                using var form = new SetupForm();
                form.Show();
                Application.DoEvents();
                using var bitmap = new Bitmap(form.Width, form.Height);
                form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, form.Size));
                bitmap.Save(args[1], ImageFormat.Png);
                return 0;
            }
            catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
        }
        ApplicationConfiguration.Initialize();
        Application.Run(new SetupForm());
        return 0;
    }
}

internal static class RibbonMerger
{
    public static bool Verify(string path)
    {
        var ribbon = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        var workbenches = ribbon["workbenches"]!.AsObject();
        var part = workbenches["PartDesignWorkbench"]!.AsObject();
        var sketch = workbenches["SketcherWorkbench"]!.AsObject();
        var partOrder = part["toolbars"]!["order"]!.AsArray();
        var sketchOrder = sketch["toolbars"]!["order"]!.AsArray();
        var surface = workbenches["SurfaceWorkbench"]!.AsObject();
        var surfaceOrder = surface["toolbars"]!["order"]!.AsArray();
        var partTools = workbenches["PartWorkbench"]!.AsObject();
        var partToolsOrder = partTools["toolbars"]!["order"]!.AsArray();
        var authoritative = ribbon["authoritativeWorkbenches"]!.AsArray();
        return partOrder[0]!.GetValue<string>() == "Fusion Sketch Entry_newPanel"
            && partOrder[1]!.GetValue<string>() == "Fusion Create_newPanel"
            && sketchOrder[0]!.GetValue<string>() == "Fusion Sketch Create_newPanel"
            && sketchOrder[3]!.GetValue<string>() == "Fusion Sketch Configure_newPanel"
            && sketchOrder[4]!.GetValue<string>() == "Fusion Sketch Inspect_newPanel"
            && sketchOrder[5]!.GetValue<string>() == "Fusion Sketch Insert_newPanel"
            && sketchOrder[6]!.GetValue<string>() == "Fusion Sketch Select_newPanel"
            && sketchOrder[^1]!.GetValue<string>() == "Fusion Finish_newPanel"
            && surfaceOrder[0]!.GetValue<string>() == "Fusion Surface Create_newPanel"
            && partToolsOrder[0]!.GetValue<string>() == "Fusion Part Create_newPanel"
            && authoritative.Any(node => node!.GetValue<string>() == "PartDesignWorkbench")
            && authoritative.Any(node => node!.GetValue<string>() == "SketcherWorkbench")
            && authoritative.Any(node => node!.GetValue<string>() == "SurfaceWorkbench")
            && authoritative.Any(node => node!.GetValue<string>() == "PartWorkbench")
            && partOrder.All(node => !node!.GetValue<string>().Contains("View", StringComparison.OrdinalIgnoreCase))
            && sketchOrder.All(node => !node!.GetValue<string>().Contains("View", StringComparison.OrdinalIgnoreCase))
            && part["toolbars"]!["Fusion Sketch Entry_newPanel"]!["commands"]!["FusionMyFreeCAD_CreateSketch"] is not null
            && part["toolbars"]!["Fusion Create_newPanel"]!["commands"]!["PartDesign_Pad"] is not null
            && part["toolbars"]!["Fusion Modify_newPanel"]!["commands"]!["PartDesign_Fillet"] is not null
            && part["toolbars"]!["Fusion Construct_newPanel"]!["commands"]!["PartDesign_SubShapeBinder"] is not null
            && part["toolbars"]!["Fusion Parameters_newPanel"]!["commands"]!["FusionMyFreeCAD_ParameterTable"] is not null
            && partTools["toolbars"]!["Fusion Part Boolean_newPanel"]!["commands"]!["Part_BooleanFragments"] is not null
            && partTools["toolbars"]!["Fusion Part Repair_newPanel"]!["commands"]!["Part_RefineShape"] is not null
            && sketch["toolbars"]!["Fusion Sketch Modify_newPanel"]!["commands"]!["Sketcher_Trimming"] is not null
            && sketch["toolbars"]!["Fusion Sketch Entry_newPanel"] is null
            && sketch["toolbars"]!["Fusion Sketch Frequent_newPanel"] is null
            && sketch["toolbars"]!["Fusion Sketch Inspect_newPanel"]!["commands"]!["Sketcher_SelectElementsWithDoFs"] is not null
            && sketch["toolbars"]!["Fusion Sketch Insert_newPanel"]!["commands"]!["Sketcher_CarbonCopy"] is not null
            && sketch["toolbars"]!["Fusion Sketch Select_newPanel"]!["commands"]!["Sketcher_SelectConstraints"] is not null
            && sketch["toolbars"]!["Fusion Sketch Create_newPanel"]!["commands"]!["Sketcher_CreateRectangle_Center"] is not null
            && sketch["toolbars"]!["Fusion Sketch Constraints_newPanel"]!["commands"]!["Sketcher_Dimension"]!["text"]!.GetValue<string>() == "Smart Dimension"
            && surface["toolbars"]!["Fusion Surface Create_newPanel"]!["commands"]!["Surface_Filling"] is not null;
    }

    public static void Merge(string basePath, string specPath, string destination)
    {
        var ribbon = JsonNode.Parse(File.ReadAllText(basePath))!.AsObject();
        var spec = JsonNode.Parse(File.ReadAllText(specPath))!.AsObject();
        var dropdowns = ribbon["dropdownButtons"]!.AsObject();
        foreach (var item in spec["dropdownButtons"]!.AsObject()) dropdowns[item.Key] = item.Value!.DeepClone();

        var allNewPanels = ribbon["newPanels"]!.AsObject();
        var allWorkbenches = ribbon["workbenches"]!.AsObject();
        ribbon["authoritativeWorkbenches"] = new JsonArray(
            spec["workbenches"]!.AsObject().Select(item => (JsonNode?)JsonValue.Create(item.Key)).ToArray()
        );
        foreach (var workbench in spec["workbenches"]!.AsObject())
        {
            var toolbars = new JsonObject();
            var panelOrder = new JsonArray();
            var newPanels = new JsonObject();
            foreach (var panelNode in workbench.Value!.AsArray())
            {
                var panel = panelNode!.AsObject();
                var name = panel["name"]!.GetValue<string>();
                var commands = new JsonObject();
                var commandOrder = new JsonArray();
                var newPanelCommands = new JsonArray();
                foreach (var entryNode in panel["commands"]!.AsArray())
                {
                    var entry = entryNode!.AsArray();
                    var command = entry[0]!.GetValue<string>();
                    commandOrder.Add(command);
                    newPanelCommands.Add(new JsonArray(command, entry[1]!.GetValue<string>()));
                    commands[command] = new JsonObject
                    {
                        ["size"] = entry[2]!.GetValue<string>(),
                        ["text"] = entry[3]!.GetValue<string>(),
                        ["icon"] = entry[4]!.GetValue<string>(),
                        ["IsExtra"] = true
                    };
                }
                panelOrder.Add(name);
                newPanels[name] = newPanelCommands;
                toolbars[name] = new JsonObject
                {
                    ["title"] = panel["title"]!.GetValue<string>(),
                    ["Enabled"] = true,
                    ["order"] = commandOrder,
                    ["commands"] = commands
                };
            }
            toolbars["order"] = panelOrder;
            allNewPanels[workbench.Key] = newPanels;
            allWorkbenches[workbench.Key] = new JsonObject { ["toolbars"] = toolbars };
        }
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        File.WriteAllText(destination, ribbon.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }
}

internal sealed class SetupForm : Form
{
    private readonly string projectRoot;
    private readonly string profile;
    private readonly string packageVersion;
    private LauncherSettingsData launcherSettings;
    private readonly Label stateLabel = new();
    private readonly Label detailLabel = new();
    private readonly TextBox logBox = new();
    private readonly Button installButton = new();
    private readonly Button repairButton = new();
    private readonly Button verifyButton = new();
    private readonly Button restoreButton = new();
    private readonly ProgressBar progress = new();
    private readonly ListView installationsList = new();
    private readonly Label launchDetailLabel = new();
    private readonly Button launchButton = new();
    private readonly Button removeBuildButton = new();
    private readonly Button refreshBuildsButton = new();
    private readonly Button addBuildButton = new();
    internal string ProjectRoot => projectRoot;
    internal string PackageVersion => packageVersion;

    public SetupForm()
    {
        projectRoot = FindProjectRoot();
        profile = FindProfile();
        packageVersion = FindPackageVersion(projectRoot);
        launcherSettings = LauncherSettings.Load();
        Text = "FusionMyFreeCAD";
        AutoScaleMode = AutoScaleMode.None;
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(820, 620);
        Size = new Size(920, 700);
        BackColor = Color.FromArgb(246, 248, 251);
        Font = new Font("Segoe UI", 10F);
        BuildInterface();
        RefreshState();
        RefreshInstallations();
    }

    private void BuildInterface()
    {
        var title = new Label { Text = "FusionMyFreeCAD", Font = new Font("Segoe UI Semibold", 22F), ForeColor = Color.FromArgb(32, 43, 56), AutoSize = true, Location = new Point(26, 18) };
        var subtitle = new Label { Text = "Find, launch, and equip every FreeCAD build on this computer.", ForeColor = Color.FromArgb(80, 91, 105), AutoSize = true, Location = new Point(30, 61) };
        var tabs = new TabControl { Name = "MainTabs", Location = new Point(24, 92), Size = new Size(854, 528), Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right };
        var launchPage = new TabPage("Launch FreeCAD") { BackColor = Color.FromArgb(246, 248, 251) };
        var setupPage = new TabPage("Install & Repair") { BackColor = Color.FromArgb(246, 248, 251) };
        Controls.AddRange([title, subtitle, tabs]);
        tabs.TabPages.Add(launchPage);
        tabs.TabPages.Add(setupPage);
        BuildLauncherPage(launchPage);
        BuildSetupPage(setupPage);
    }

    private void BuildLauncherPage(TabPage page)
    {
        var intro = new Label
        {
            Text = "Detected releases and source builds",
            Font = new Font("Segoe UI Semibold", 14F),
            ForeColor = Color.FromArgb(32, 43, 56),
            AutoSize = true,
            Location = new Point(18, 18)
        };
        var help = new Label
        {
            Text = "Double-click a build to run it. Add Build remembers executables in unusual locations.",
            ForeColor = Color.FromArgb(80, 91, 105),
            AutoSize = true,
            Location = new Point(20, 52)
        };
        installationsList.Location = new Point(18, 82);
        installationsList.Name = "InstallationsList";
        installationsList.Size = new Size(798, 292);
        installationsList.Anchor = AnchorStyles.Top | AnchorStyles.Left;
        installationsList.View = View.Details;
        installationsList.BackColor = Color.White;
        installationsList.ForeColor = Color.FromArgb(32, 43, 56);
        installationsList.BorderStyle = BorderStyle.FixedSingle;
        installationsList.HeaderStyle = ColumnHeaderStyle.Nonclickable;
        installationsList.FullRowSelect = true;
        installationsList.HideSelection = false;
        installationsList.MultiSelect = false;
        installationsList.Columns.Add("Version", 150);
        installationsList.Columns.Add("Build", 120);
        installationsList.Columns.Add("Executable", 430);
        installationsList.Columns.Add("Detected by", 110);
        installationsList.SelectedIndexChanged += (_, _) => UpdateLaunchSelection();
        installationsList.DoubleClick += (_, _) => LaunchSelected();

        launchDetailLabel.Location = new Point(20, 384);
        launchDetailLabel.Size = new Size(790, 42);
        launchDetailLabel.Anchor = AnchorStyles.Top | AnchorStyles.Left;
        launchDetailLabel.ForeColor = Color.FromArgb(80, 91, 105);

        ConfigureLauncherButton(refreshBuildsButton, "Refresh", 18, 100);
        refreshBuildsButton.Click += (_, _) => RefreshInstallations();
        ConfigureLauncherButton(addBuildButton, "Add Build…", 128, 120);
        addBuildButton.Click += (_, _) => AddBuild();
        ConfigureLauncherButton(removeBuildButton, "Forget", 258, 100);
        removeBuildButton.Click += (_, _) => RemoveSelectedBuild();
        ConfigureLauncherButton(launchButton, "Launch FreeCAD", 636, 180);
        launchButton.Name = "LaunchButton";
        launchButton.Anchor = AnchorStyles.Top | AnchorStyles.Left;
        launchButton.BackColor = Color.FromArgb(20, 116, 204);
        launchButton.ForeColor = Color.White;
        launchButton.FlatStyle = FlatStyle.Flat;
        launchButton.FlatAppearance.BorderSize = 0;
        launchButton.Click += (_, _) => LaunchSelected();

        page.Controls.AddRange([intro, help, installationsList, launchDetailLabel, refreshBuildsButton, addBuildButton, removeBuildButton, launchButton]);
    }

    private static void ConfigureLauncherButton(Button button, string text, int x, int width)
    {
        button.Text = text;
        button.Location = new Point(x, 438);
        button.Size = new Size(width, 40);
        button.Anchor = AnchorStyles.Top | AnchorStyles.Left;
    }

    private void BuildSetupPage(TabPage page)
    {
        var card = new Panel { BackColor = Color.White, Location = new Point(18, 18), Size = new Size(798, 112), Anchor = AnchorStyles.Top | AnchorStyles.Left };
        stateLabel.Font = new Font("Segoe UI Semibold", 14F);
        stateLabel.ForeColor = Color.FromArgb(32, 43, 56);
        stateLabel.Location = new Point(18, 16);
        stateLabel.AutoSize = true;
        detailLabel.ForeColor = Color.FromArgb(80, 91, 105);
        detailLabel.Location = new Point(20, 52);
        detailLabel.Size = new Size(750, 50);
        card.Controls.Add(stateLabel);
        card.Controls.Add(detailLabel);

        ConfigureButton(installButton, "Install / Upgrade", 18, 180);
        installButton.Name = "InstallButton";
        installButton.BackColor = Color.FromArgb(20, 116, 204);
        installButton.ForeColor = Color.White;
        installButton.FlatStyle = FlatStyle.Flat;
        installButton.FlatAppearance.BorderSize = 0;
        installButton.Click += async (_, _) => await RunSetup("Install");
        ConfigureButton(repairButton, "Repair", 210, 120);
        repairButton.Click += async (_, _) => await RunSetup("Repair");
        ConfigureButton(verifyButton, "Verify", 342, 120);
        verifyButton.Click += async (_, _) => await RunSetup("Verify");
        ConfigureButton(restoreButton, "Restore Previous UI", 474, 178);
        restoreButton.Click += async (_, _) => await RestorePrevious();

        progress.Location = new Point(18, 202);
        progress.Size = new Size(798, 5);
        progress.Anchor = AnchorStyles.Top | AnchorStyles.Left;
        progress.Style = ProgressBarStyle.Marquee;
        progress.Visible = false;
        logBox.Location = new Point(18, 222);
        logBox.Size = new Size(798, 256);
        logBox.Anchor = AnchorStyles.Top | AnchorStyles.Left;
        logBox.Multiline = true;
        logBox.ReadOnly = true;
        logBox.ScrollBars = ScrollBars.Vertical;
        logBox.BackColor = Color.White;
        logBox.BorderStyle = BorderStyle.FixedSingle;
        logBox.Text = "Ready.";
        page.Controls.AddRange([card, installButton, repairButton, verifyButton, restoreButton, progress, logBox]);
    }

    private static void ConfigureButton(Button button, string text, int x, int width)
    {
        button.Text = text;
        button.Location = new Point(x, 146);
        button.Size = new Size(width, 42);
    }

    private void RefreshInstallations()
    {
        var selectedPath = installationsList.SelectedItems.Count == 1
            ? ((FreeCadInstallation)installationsList.SelectedItems[0].Tag!).ExecutablePath
            : launcherSettings.LastExecutable;
        var installations = FreeCadDiscovery.Discover(projectRoot, launcherSettings.CustomExecutables);
        installationsList.BeginUpdate();
        installationsList.Items.Clear();
        ListViewItem? selectedItem = null;
        foreach (var installation in installations)
        {
            var item = new ListViewItem([installation.Version, installation.Kind, installation.ExecutablePath, installation.Source]) { Tag = installation };
            installationsList.Items.Add(item);
            if (string.Equals(installation.ExecutablePath, selectedPath, StringComparison.OrdinalIgnoreCase)) selectedItem = item;
        }
        installationsList.EndUpdate();
        selectedItem ??= installationsList.Items.Count > 0 ? installationsList.Items[0] : null;
        if (selectedItem is not null) selectedItem.Selected = true;
        UpdateLaunchSelection();
    }

    private void UpdateLaunchSelection()
    {
        var installation = SelectedInstallation();
        launchButton.Enabled = installation is not null;
        removeBuildButton.Enabled = installation is not null && launcherSettings.CustomExecutables.Any(path => string.Equals(path, installation.ExecutablePath, StringComparison.OrdinalIgnoreCase));
        launchDetailLabel.Text = installation is null
            ? "No FreeCAD executable was found. Choose Add Build to locate one."
            : $"{installation.Kind} · {installation.ExecutablePath}";
    }

    private FreeCadInstallation? SelectedInstallation() => installationsList.SelectedItems.Count == 1
        ? installationsList.SelectedItems[0].Tag as FreeCadInstallation
        : null;

    private void AddBuild()
    {
        using var dialog = new OpenFileDialog
        {
            Title = "Choose a FreeCAD executable",
            Filter = "FreeCAD executable (FreeCAD.exe)|FreeCAD.exe|Executable files (*.exe)|*.exe",
            CheckFileExists = true,
            Multiselect = false
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        if (!launcherSettings.CustomExecutables.Any(path => string.Equals(path, dialog.FileName, StringComparison.OrdinalIgnoreCase)))
            launcherSettings.CustomExecutables.Add(dialog.FileName);
        launcherSettings.LastExecutable = dialog.FileName;
        LauncherSettings.Save(launcherSettings);
        RefreshInstallations();
    }

    private void RemoveSelectedBuild()
    {
        var installation = SelectedInstallation();
        if (installation is null) return;
        launcherSettings.CustomExecutables.RemoveAll(path => string.Equals(path, installation.ExecutablePath, StringComparison.OrdinalIgnoreCase));
        LauncherSettings.Save(launcherSettings);
        RefreshInstallations();
    }

    private void LaunchSelected()
    {
        var installation = SelectedInstallation();
        if (installation is null) return;
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = installation.ExecutablePath,
                WorkingDirectory = Path.GetDirectoryName(installation.ExecutablePath)!,
                UseShellExecute = true
            });
            launcherSettings.LastExecutable = installation.ExecutablePath;
            LauncherSettings.Save(launcherSettings);
            launchDetailLabel.Text = $"Started {installation.Version} from {installation.ExecutablePath}";
        }
        catch (Exception error) { ShowFailure($"FreeCAD could not be started.\r\n\r\n{error.Message}"); }
    }

    private void RefreshState()
    {
        var statePath = Path.Combine(profile, "FusionMyFreeCAD-install-state.json");
        var runtimePath = Path.Combine(profile, "FusionMyFreeCAD-runtime-status.json");
        string installedVersion = "not installed";
        string runtime = "FreeCAD has not yet confirmed this layout.";
        if (File.Exists(statePath))
        {
            try
            {
                using var state = JsonDocument.Parse(File.ReadAllText(statePath));
                installedVersion = state.RootElement.TryGetProperty("PackageVersion", out var version) ? version.GetString() ?? "older version" : "older version";
            }
            catch { installedVersion = "installed, state needs repair"; }
        }
        if (File.Exists(runtimePath))
        {
            try
            {
                using var status = JsonDocument.Parse(File.ReadAllText(runtimePath));
                var layout = status.RootElement.TryGetProperty("layoutVersion", out var value) ? value.GetString() : "unknown";
                runtime = $"FreeCAD last loaded layout {layout}.";
            }
            catch { runtime = "FreeCAD's runtime report could not be read."; }
        }
        stateLabel.Text = $"Status: {installedVersion}";
        detailLabel.Text = $"Profile: {profile}\r\n{runtime}";
        repairButton.Enabled = File.Exists(statePath);
        restoreButton.Enabled = File.Exists(statePath);
        installButton.Text = !File.Exists(statePath)
            ? $"Install {packageVersion}"
            : string.Equals(installedVersion, packageVersion, StringComparison.OrdinalIgnoreCase)
                ? $"Reinstall {packageVersion}"
                : $"Upgrade to {packageVersion}";
    }

    private async Task RunSetup(string action)
    {
        var script = Path.Combine(projectRoot, "installer", "Setup-FusionMyFreeCAD.ps1");
        if (!File.Exists(script)) { ShowFailure("The setup engine is missing. Keep this application in the FusionMyFreeCAD project folder."); return; }
        var executable = Environment.ProcessPath ?? Application.ExecutablePath;
        await RunPowerShell(script, $"-Action {action} -FreeCADUserDir \"{profile}\" -SetupExecutable \"{executable}\"");
        RefreshState();
    }

    private async Task RestorePrevious()
    {
        if (MessageBox.Show(this, "Restore the UI that existed before FusionMyFreeCAD was first installed?", "Restore previous UI", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        await RunPowerShell(Path.Combine(projectRoot, "installer", "Uninstall-FusionMyFreeCAD.ps1"), $"-FreeCADUserDir \"{profile}\"");
        RefreshState();
    }

    private async Task RunPowerShell(string script, string arguments)
    {
        SetBusy(true);
        logBox.Text = "Working…\r\n";
        try
        {
            var start = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = $"-NoLogo -NoProfile -ExecutionPolicy Bypass -File \"{script}\" {arguments}",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = projectRoot
            };
            using var process = Process.Start(start) ?? throw new InvalidOperationException("Windows could not start the setup engine.");
            var outputTask = process.StandardOutput.ReadToEndAsync();
            var errorTask = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            var output = await outputTask;
            var error = await errorTask;
            logBox.Text = string.IsNullOrWhiteSpace(output) ? error : output + (string.IsNullOrWhiteSpace(error) ? "" : "\r\n" + error);
            if (process.ExitCode == 0) MessageBox.Show(this, "Completed successfully. Restart FreeCAD to load ribbon changes.", "FusionMyFreeCAD", MessageBoxButtons.OK, MessageBoxIcon.Information);
            else ShowFailure(string.IsNullOrWhiteSpace(error) ? "Verification found a problem. See the setup details." : error.Trim());
        }
        catch (Exception error) { ShowFailure(error.Message); }
        finally { SetBusy(false); }
    }

    private void SetBusy(bool busy)
    {
        progress.Visible = busy;
        installButton.Enabled = !busy;
        repairButton.Enabled = !busy;
        verifyButton.Enabled = !busy;
        restoreButton.Enabled = !busy;
        refreshBuildsButton.Enabled = !busy;
        addBuildButton.Enabled = !busy;
        if (busy)
        {
            launchButton.Enabled = false;
            removeBuildButton.Enabled = false;
        }
        else UpdateLaunchSelection();
        UseWaitCursor = busy;
    }

    private void ShowFailure(string message) => MessageBox.Show(this, message, "FusionMyFreeCAD setup", MessageBoxButtons.OK, MessageBoxIcon.Error);

    private static string FindProfile()
    {
        var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "FreeCAD");
        var preferred = Path.Combine(root, "v1-1");
        if (File.Exists(Path.Combine(preferred, "user.cfg"))) return preferred;
        if (Directory.Exists(root))
        {
            var found = Directory.GetDirectories(root).Where(path => File.Exists(Path.Combine(path, "user.cfg"))).OrderByDescending(Directory.GetLastWriteTimeUtc).FirstOrDefault();
            if (found is not null) return found;
        }
        return preferred;
    }

    private static string FindProjectRoot()
    {
        var executableDirectory = Path.GetDirectoryName(Environment.ProcessPath ?? Application.ExecutablePath);
        var directory = new DirectoryInfo(executableDirectory ?? AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "installer", "Setup-FusionMyFreeCAD.ps1"))) return directory.FullName;
            directory = directory.Parent;
        }
        return AppContext.BaseDirectory;
    }

    private static string FindPackageVersion(string root)
    {
        var candidates = new[]
        {
            Path.Combine(root, "package.xml"),
            Path.Combine(root, "installer", "assets", "FusionMyFreeCAD", "package.xml")
        };
        foreach (var path in candidates.Where(File.Exists))
        {
            try
            {
                var version = XDocument.Load(path).Descendants().FirstOrDefault(node => node.Name.LocalName == "version")?.Value.Trim();
                if (!string.IsNullOrWhiteSpace(version)) return version;
            }
            catch { }
        }
        return Application.ProductVersion.Split('+')[0];
    }
}

internal sealed record FreeCadInstallation(string ExecutablePath, string Version, string Kind, string Source);

internal sealed class LauncherSettingsData
{
    public List<string> CustomExecutables { get; set; } = [];
    public string? LastExecutable { get; set; }
}

internal static class LauncherSettings
{
    private static readonly string SettingsPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "FusionMyFreeCAD",
        "launcher.json"
    );

    public static LauncherSettingsData Load()
    {
        try
        {
            return File.Exists(SettingsPath)
                ? JsonSerializer.Deserialize<LauncherSettingsData>(File.ReadAllText(SettingsPath)) ?? new LauncherSettingsData()
                : new LauncherSettingsData();
        }
        catch { return new LauncherSettingsData(); }
    }

    public static void Save(LauncherSettingsData settings)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(SettingsPath)!);
        var temporary = SettingsPath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(settings, new JsonSerializerOptions { WriteIndented = true }));
        File.Move(temporary, SettingsPath, true);
    }
}

internal static class FreeCadDiscovery
{
    public static IReadOnlyList<FreeCadInstallation> Discover(string projectRoot, IEnumerable<string> customExecutables)
    {
        var candidates = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        void Add(string? executable, string source)
        {
            if (string.IsNullOrWhiteSpace(executable)) return;
            var cleaned = executable.Trim().Trim('"');
            var comma = cleaned.IndexOf(',');
            if (comma > 0) cleaned = cleaned[..comma];
            try { cleaned = Path.GetFullPath(Environment.ExpandEnvironmentVariables(cleaned)); }
            catch { return; }
            if (File.Exists(cleaned) && string.Equals(Path.GetFileName(cleaned), "FreeCAD.exe", StringComparison.OrdinalIgnoreCase))
                candidates.TryAdd(cleaned, source);
        }

        AddRegistryCandidates(Add);
        AddPathCandidates(Add);
        AddCommonInstallCandidates(Add);
        AddShortcutCandidates(Add);
        AddPortableCandidates(Add);
        AddSourceBuildCandidates(projectRoot, Add);
        foreach (var executable in customExecutables) Add(executable, "Saved");

        return candidates.Select(item => Describe(item.Key, item.Value))
            .OrderBy(item => item.Kind == "Installed" ? 0 : item.Kind == "Source build" ? 1 : 2)
            .ThenByDescending(item => item.Version, StringComparer.OrdinalIgnoreCase)
            .ThenBy(item => item.ExecutablePath, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static FreeCadInstallation Describe(string executable, string source)
    {
        var normalized = executable.Replace('/', '\\');
        var sourceBuild = normalized.Contains("\\build\\", StringComparison.OrdinalIgnoreCase)
            || normalized.Contains("\\.pixi\\", StringComparison.OrdinalIgnoreCase);
        var kind = sourceBuild ? "Source build" : source == "Saved" ? "Custom" : "Installed";
        string version;
        try
        {
            var info = FileVersionInfo.GetVersionInfo(executable);
            version = FirstUsefulVersion(info.ProductVersion, info.FileVersion) ?? "Unknown version";
        }
        catch { version = "Unknown version"; }
        if (version == "Unknown version" && sourceBuild)
            version = TryReadSourceVersion(executable) ?? version;
        if (version == "Unknown version" && !sourceBuild)
            version = TryReadCommandVersion(executable) ?? version;
        return new FreeCadInstallation(executable, version, kind, source);
    }

    private static string? FirstUsefulVersion(params string?[] values) => values.FirstOrDefault(value =>
        !string.IsNullOrWhiteSpace(value) && value != "0.0.0.0" && value != "0.0.0");

    private static string? TryReadCommandVersion(string executable)
    {
        var command = Path.Combine(Path.GetDirectoryName(executable)!, "FreeCADCmd.exe");
        if (!File.Exists(command)) return null;
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = command,
                Arguments = "--version",
                WorkingDirectory = Path.GetDirectoryName(command)!,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            });
            if (process is null) return null;
            var output = process.StandardOutput.ReadToEnd();
            if (!process.WaitForExit(3000))
            {
                try { process.Kill(true); }
                catch { }
                return null;
            }
            foreach (var line in output.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
            {
                var marker = line.IndexOf("FreeCAD ", StringComparison.OrdinalIgnoreCase);
                if (marker < 0) continue;
                var remainder = line[(marker + "FreeCAD ".Length)..].Trim();
                var version = remainder.Split([',', ' '], StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
                if (!string.IsNullOrWhiteSpace(version)) return version;
            }
        }
        catch { }
        return null;
    }

    private static string? TryReadSourceVersion(string executable)
    {
        DirectoryInfo? directory = new(Path.GetDirectoryName(executable)!);
        DirectoryInfo? repository = null;
        for (var depth = 0; directory is not null && depth < 10; depth++, directory = directory.Parent)
        {
            if (File.Exists(Path.Combine(directory.FullName, "src", "Build", "Version.h.cmake")))
            {
                repository = directory;
                break;
            }
        }
        if (repository is null) return null;

        var candidates = new List<string>();
        var normalized = executable.Replace('/', '\\');
        var buildMarker = normalized.IndexOf("\\build\\", StringComparison.OrdinalIgnoreCase);
        if (buildMarker >= 0)
        {
            var afterBuild = normalized[(buildMarker + "\\build\\".Length)..];
            var configuration = afterBuild.Split('\\', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault();
            if (configuration is not null)
                candidates.Add(Path.Combine(repository.FullName, "build", configuration, "src", "Build", "Version.h"));
        }
        var buildRoot = Path.Combine(repository.FullName, "build");
        if (Directory.Exists(buildRoot))
        {
            try
            {
                candidates.AddRange(Directory.EnumerateDirectories(buildRoot)
                    .Select(path => Path.Combine(path, "src", "Build", "Version.h"))
                    .OrderByDescending(path => File.Exists(path) ? File.GetLastWriteTimeUtc(path) : DateTime.MinValue));
            }
            catch { }
        }
        foreach (var path in candidates.Distinct(StringComparer.OrdinalIgnoreCase).Where(File.Exists))
        {
            try
            {
                var values = File.ReadLines(path)
                    .Where(line => line.StartsWith("#define FCVersion", StringComparison.Ordinal))
                    .Select(line => line.Split(' ', StringSplitOptions.RemoveEmptyEntries))
                    .Where(parts => parts.Length >= 3)
                    .ToDictionary(parts => parts[1], parts => parts[2].Trim('"'));
                if (!values.TryGetValue("FCVersionMajor", out var major) || !values.TryGetValue("FCVersionMinor", out var minor)) continue;
                values.TryGetValue("FCVersionPoint", out var point);
                values.TryGetValue("FCVersionSuffix", out var suffix);
                var result = $"{major}.{minor}.{point ?? "0"}";
                return string.IsNullOrWhiteSpace(suffix) ? result : $"{result}-{suffix}";
            }
            catch { }
        }
        return null;
    }

    private static void AddRegistryCandidates(Action<string?, string> add)
    {
        var views = Environment.Is64BitOperatingSystem ? new[] { RegistryView.Registry64, RegistryView.Registry32 } : new[] { RegistryView.Default };
        foreach (var hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
        foreach (var view in views)
        {
            try
            {
                using var root = RegistryKey.OpenBaseKey(hive, view);
                using var uninstall = root.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall");
                if (uninstall is null) continue;
                foreach (var name in uninstall.GetSubKeyNames())
                {
                    using var entry = uninstall.OpenSubKey(name);
                    var displayName = entry?.GetValue("DisplayName") as string;
                    if (displayName?.Contains("FreeCAD", StringComparison.OrdinalIgnoreCase) != true) continue;
                    var location = entry?.GetValue("InstallLocation") as string;
                    if (!string.IsNullOrWhiteSpace(location))
                    {
                        add(Path.Combine(location, "bin", "FreeCAD.exe"), "Installed apps");
                        add(Path.Combine(location, "FreeCAD.exe"), "Installed apps");
                    }
                    add(entry?.GetValue("DisplayIcon") as string, "Installed apps");
                }
            }
            catch { }
        }
    }

    private static void AddPathCandidates(Action<string?, string> add)
    {
        foreach (var directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            try { add(Path.Combine(directory.Trim(), "FreeCAD.exe"), "PATH"); }
            catch { }
        }
    }

    private static void AddCommonInstallCandidates(Action<string?, string> add)
    {
        var roots = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs")
        };
        foreach (var root in roots.Where(Directory.Exists))
        {
            try
            {
                foreach (var directory in Directory.EnumerateDirectories(root, "*FreeCAD*", SearchOption.TopDirectoryOnly))
                {
                    add(Path.Combine(directory, "bin", "FreeCAD.exe"), "Common folders");
                    add(Path.Combine(directory, "FreeCAD.exe"), "Common folders");
                }
            }
            catch { }
        }
    }

    private static void AddShortcutCandidates(Action<string?, string> add)
    {
        var roots = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory),
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned")
        };
        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType is null) return;
        object? shell = null;
        try
        {
            shell = Activator.CreateInstance(shellType);
            if (shell is null) return;
            foreach (var root in roots.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase))
            {
                IEnumerable<string> shortcuts;
                try { shortcuts = Directory.EnumerateFiles(root, "*.lnk", SearchOption.AllDirectories).ToArray(); }
                catch { continue; }
                foreach (var path in shortcuts)
                {
                    try
                    {
                        dynamic shortcut = shellType.InvokeMember(
                            "CreateShortcut",
                            System.Reflection.BindingFlags.InvokeMethod,
                            null,
                            shell,
                            [path])!;
                        var target = shortcut.TargetPath as string;
                        if (string.Equals(Path.GetFileName(target), "FreeCAD.exe", StringComparison.OrdinalIgnoreCase))
                            add(target, "Windows shortcut");
                    }
                    catch { }
                }
            }
        }
        catch { }
        finally
        {
            if (shell is not null && System.Runtime.InteropServices.Marshal.IsComObject(shell))
                System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
        }
    }

    private static void AddPortableCandidates(Action<string?, string> add)
    {
        foreach (var drive in DriveInfo.GetDrives())
        {
            try
            {
                if (!drive.IsReady) continue;
                var root = drive.RootDirectory.FullName;
                add(Path.Combine(root, "Portable Programs", "FreeCAD", "bin", "FreeCAD.exe"), "Portable folders");
                add(Path.Combine(root, "Programs", "FreeCAD", "bin", "FreeCAD.exe"), "Portable folders");
            }
            catch { }
        }
    }

    private static void AddSourceBuildCandidates(string projectRoot, Action<string?, string> add)
    {
        var parent = Directory.GetParent(projectRoot)?.FullName;
        if (parent is null) return;
        var likelyRoots = new[] { Path.Combine(parent, "FreeCAD"), projectRoot };
        var relativeExecutables = new[]
        {
            @"build\bin\FreeCAD.exe",
            @"build\release\bin\FreeCAD.exe",
            @"build\debug\bin\FreeCAD.exe",
            @"build\RelWithDebInfo\bin\FreeCAD.exe",
            @".pixi\envs\default\Library\bin\FreeCAD.exe"
        };
        foreach (var root in likelyRoots.Distinct(StringComparer.OrdinalIgnoreCase))
        foreach (var relative in relativeExecutables)
            add(Path.Combine(root, relative), "Source workspace");
    }
}
