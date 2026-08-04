using System.IO;
using System.Text.Json;

namespace Centesimo.Desktop.Services;

/// <summary>
/// Impostazioni locali del client (non contengono segreti: il token sta nel
/// Credential Manager, vedi <see cref="TokenStore"/>).
/// File: <c>%APPDATA%\Centesimo\settings.json</c>.
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
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Centesimo");

    private static string ConfigPath => Path.Combine(ConfigDirectory, "settings.json");

    /// <summary>
    /// Perché l'ultimo <see cref="Load"/> ha dovuto ripiegare sui valori predefiniti,
    /// oppure <c>null</c> se è andato a buon fine. Va mostrato all'utente: un
    /// <c>settings.json</c> illeggibile si manifesterebbe altrimenti come un
    /// inspiegabile "punta a localhost e non si collega".
    /// </summary>
    public static string? LastLoadError { get; private set; }

    public static AppSettings Load()
    {
        LastLoadError = null;

        if (!File.Exists(ConfigPath))
        {
            // Primo avvio: nessun errore da segnalare, si parte dai valori predefiniti.
            return new AppSettings { ServerCertificatePath = GuessCertificatePath() };
        }

        try
        {
            var loaded = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(ConfigPath));
            if (loaded is not null)
            {
                // Non basta che il percorso sia valorizzato: se punta a un file che non
                // c'è più, il pinning resterebbe disattivato in silenzio e ogni
                // connessione fallirebbe con "certificato rifiutato". Meglio riprovare la
                // ricerca automatica, che guarda anche in <repo>/server/certs.
                if (loaded.ServerCertificatePath is null || !File.Exists(loaded.ServerCertificatePath))
                {
                    loaded.ServerCertificatePath = GuessCertificatePath();
                }
                return loaded;
            }

            LastLoadError = $"{ConfigPath} non contiene un oggetto JSON: uso i valori predefiniti.";
        }
        catch (Exception ex)
        {
            // Un settings.json corrotto non deve impedire l'avvio, ma non deve nemmeno
            // passare in silenzio.
            LastLoadError = $"{ConfigPath} non è leggibile ({ex.Message}). Uso i valori predefiniti.";
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
    /// cartelle di build, poi in <c>%APPDATA%\Centesimo\server.crt</c>.
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
