using System.Net.Http;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Centesimo.Desktop.ViewModels;

/// <summary>
/// Login (§1.1). La password vive solo nel PasswordBox e nella chiamata HTTP: non viene
/// salvata da nessuna parte. Quello che resta sul disco è il refresh token, dentro il
/// Windows Credential Manager.
/// </summary>
public partial class LoginViewModel : ObservableObject
{
    [ObservableProperty] private string _username = string.Empty;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string _serverUrl = App.Api.Client.Settings.ApiBaseUrl;

    /// <summary>
    /// Mostra i percorsi risolti, non solo l'esito: quando il pinning non parte serve
    /// sapere <b>quale</b> file l'app stava cercando, altrimenti l'unico sintomo è un
    /// generico "certificato rifiutato".
    /// </summary>
    public string CertificateInfo => App.Api.Client.Settings.ServerCertificatePath is { } path
        ? $"Certificato pinnato: {path}"
        : $"Nessun certificato pinnato — cercato in <repo>\\server\\certs\\server.crt e in " +
          $"{Services.AppSettings.ConfigDirectory}\\server.crt. Senza, il certificato " +
          $"self-signed del server viene rifiutato.";

    /// <summary>Avviso se <c>settings.json</c> non è stato caricato, vuoto altrimenti.</summary>
    public string? ConfigWarning => Services.AppSettings.LastLoadError;

    public async Task<bool> LoginAsync(string password)
    {
        IsBusy = true;
        ErrorMessage = null;
        try
        {
            var url = (ServerUrl ?? string.Empty).Trim().TrimEnd('/');
            if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) ||
                (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp))
            {
                ErrorMessage = "Indirizzo del server non valido: serve un URL assoluto, " +
                               "per esempio https://192.168.1.104:8443";
                return false;
            }

            App.UseServer(url);
            await App.Api.Client.LoginAsync(Username, password);
            // L'indirizzo si è dimostrato funzionante: solo ora diventa quello salvato.
            App.Api.Client.Settings.Save();
            return true;
        }
        catch (Services.ApiException ex)
        {
            ErrorMessage = ex.Message;
            return false;
        }
        catch (HttpRequestException ex)
        {
            // Il messaggio esterno è quasi sempre generico ("The SSL connection could not
            // be established"): la ragione vera sta nelle eccezioni annidate, ed è la
            // differenza fra "certificato non combacia" e "nessuno in ascolto".
            var causes = new List<string>();
            for (var inner = ex.InnerException; inner is not null; inner = inner.InnerException)
            {
                causes.Add(inner.Message);
            }

            ErrorMessage = $"Server non raggiungibile su {App.Api.Client.Settings.ApiBaseUrl}\n" +
                           ex.Message +
                           (causes.Count > 0 ? "\n→ " + string.Join("\n→ ", causes) : string.Empty);
            return false;
        }
        finally
        {
            IsBusy = false;
        }
    }
}
