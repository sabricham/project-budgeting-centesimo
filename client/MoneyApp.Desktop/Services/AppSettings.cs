using System.IO;
using System.Text.Json;

namespace MoneyApp.Desktop.Services;

/// <summary>
/// Impostazioni locali del client (non contengono segreti: il token sta nel
/// Credential Manager, vedi <see cref="TokenStore"/>).
/// File: <c>%APPDATA%\MoneyApp\settings.json</c>.
/// </summary>
public sealed class AppSettings
{
    public string ApiBaseUrl { get; set; } = "https://localhost:8443";

    /// <summary>
    /// Percorso del certificato del server. In sviluppo è il self-signed generato dal
    /// container in <c>server/certs/server.crt</c>: il client lo "pinna" invece di
    /// disattivare la verifica TLS (§1.1).
    /// </summary>
    public string? ServerCertificatePath { get; set; }

    public static string ConfigDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "MoneyApp");

    private static string ConfigPath => Path.Combine(ConfigDirectory, "settings.json");

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(ConfigPath))
            {
                var loaded = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(ConfigPath));
                if (loaded is not null)
                {
                    loaded.ServerCertificatePath ??= GuessCertificatePath();
                    return loaded;
                }
            }
        }
        catch (Exception)
        {
            // Un settings.json corrotto non deve impedire l'avvio: si riparte dai default.
        }

        return new AppSettings { ServerCertificatePath = GuessCertificatePath() };
    }

    public void Save()
    {
        Directory.CreateDirectory(ConfigDirectory);
        File.WriteAllText(ConfigPath,
            JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true }));
    }

    /// <summary>
    /// Cerca il certificato in <c>&lt;repo&gt;/server/certs/server.crt</c> risalendo dalle
    /// cartelle di build, poi in <c>%APPDATA%\MoneyApp\server.crt</c>.
    /// </summary>
    private static string? GuessCertificatePath()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        for (var i = 0; i < 8 && directory is not null; i++, directory = directory.Parent)
        {
            var candidate = Path.Combine(directory.FullName, "server", "certs", "server.crt");
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        var appData = Path.Combine(ConfigDirectory, "server.crt");
        return File.Exists(appData) ? appData : null;
    }
}
