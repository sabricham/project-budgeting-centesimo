using System.Globalization;
using System.Windows;
using System.Windows.Markup;
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
        UseItalianFormatting();

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
    /// Numeri e date in formato italiano ovunque: virgola decimale, punto per le migliaia,
    /// date gg/mm/aaaa.
    ///
    /// Le due righe non bastano da sole: WPF ignora la cultura del thread nei binding e usa
    /// <see cref="FrameworkElement.LanguageProperty"/>, che di default vale sempre "en-US".
    /// Senza il terzo blocco gli importi resterebbero "1,234.56" nonostante tutto il resto.
    /// Il formato sul filo con il server non cambia: resta ISO/InvariantCulture (§1.3).
    /// </summary>
    private static void UseItalianFormatting()
    {
        var culture = CultureInfo.GetCultureInfo("it-IT");
        CultureInfo.DefaultThreadCurrentCulture = culture;
        CultureInfo.DefaultThreadCurrentUICulture = culture;

        FrameworkElement.LanguageProperty.OverrideMetadata(
            typeof(FrameworkElement),
            new FrameworkPropertyMetadata(XmlLanguage.GetLanguage(culture.IetfLanguageTag)));
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
