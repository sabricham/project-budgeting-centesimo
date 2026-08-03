using System.Net.Http;
using CommunityToolkit.Mvvm.ComponentModel;

namespace MoneyApp.Desktop.ViewModels;

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

    public string CertificateInfo => App.Api.Client.Settings.ServerCertificatePath is { } path
        ? $"Certificato server: {path}"
        : "Nessun certificato pinnato: sarà accettato solo un certificato valido per una CA di sistema.";

    public async Task<bool> LoginAsync(string password)
    {
        IsBusy = true;
        ErrorMessage = null;
        try
        {
            await App.Api.Client.LoginAsync(Username, password);
            return true;
        }
        catch (Services.ApiException ex)
        {
            ErrorMessage = ex.Message;
            return false;
        }
        catch (HttpRequestException ex)
        {
            ErrorMessage = "Server non raggiungibile: " + ex.Message +
                           "\nVerifica che `docker compose up` sia in esecuzione.";
            return false;
        }
        finally
        {
            IsBusy = false;
        }
    }
}
