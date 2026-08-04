using System.Windows;
using Centesimo.Desktop.Services;
using Centesimo.Desktop.Views;

namespace Centesimo.Desktop;

public partial class App : Application
{
    /// <summary>
    /// Unica istanza dell'API condivisa dalle viste. Per un'app a utente singolo un
    /// contenitore di dependency injection sarebbe cerimonia senza beneficio.
    /// </summary>
    public static CentesimoApi Api { get; private set; } = null!;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        // Durante il login non esiste ancora una finestra principale: senza questo,
        // la chiusura del dialog di login farebbe terminare l'applicazione.
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        // Niente Save() qui: se settings.json fosse illeggibile, Load() ripiega sui valori
        // predefiniti e un salvataggio immediato sovrascriverebbe la configurazione buona
        // con `localhost`, cancellando l'unica traccia del problema. Si salva solo dopo un
        // login riuscito, cioè quando l'indirizzo si è dimostrato valido.
        var settings = AppSettings.Load();
        Api = new CentesimoApi(new ApiClient(settings, new TokenStore()));

        // Se c'è un refresh token valido nel Credential Manager si entra senza password (§1.1).
        var restored = await Api.Client.TryRestoreSessionAsync();
        if (restored is not null)
        {
            ShowMainWindow();
            return;
        }

        var login = new LoginWindow();
        if (login.ShowDialog() == true)
        {
            ShowMainWindow();
        }
        else
        {
            Shutdown();
        }
    }

    /// <summary>
    /// Ripunta il client su un altro indirizzo (§1.4: LAN oggi, Tailscale in mobilità).
    /// <see cref="ApiClient"/> fissa la <c>BaseAddress</c> nel costruttore, quindi cambiare
    /// server significa ricostruirlo. Da chiamare solo prima del login: i token in memoria
    /// del client precedente vengono buttati con lui.
    /// </summary>
    public static void UseServer(string baseUrl)
    {
        var settings = Api.Client.Settings;
        if (string.Equals(settings.ApiBaseUrl, baseUrl, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        settings.ApiBaseUrl = baseUrl;
        Api.Client.Dispose();
        Api = new CentesimoApi(new ApiClient(settings, new TokenStore()));
    }

    private void ShowMainWindow()
    {
        var window = new MainWindow();
        MainWindow = window;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        window.Show();
    }
}
