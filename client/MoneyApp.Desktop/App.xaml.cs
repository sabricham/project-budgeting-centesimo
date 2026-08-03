using System.Windows;
using MoneyApp.Desktop.Services;
using MoneyApp.Desktop.Views;

namespace MoneyApp.Desktop;

public partial class App : Application
{
    /// <summary>
    /// Unica istanza dell'API condivisa dalle viste. Per un'app a utente singolo un
    /// contenitore di dependency injection sarebbe cerimonia senza beneficio.
    /// </summary>
    public static MoneyApi Api { get; private set; } = null!;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        // Durante il login non esiste ancora una finestra principale: senza questo,
        // la chiusura del dialog di login farebbe terminare l'applicazione.
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        var settings = AppSettings.Load();
        settings.Save();
        Api = new MoneyApi(new ApiClient(settings, new TokenStore()));

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

    private void ShowMainWindow()
    {
        var window = new MainWindow();
        MainWindow = window;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        window.Show();
    }
}
