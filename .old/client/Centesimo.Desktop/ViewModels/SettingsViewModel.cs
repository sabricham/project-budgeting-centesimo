using System.Diagnostics;
using System.Net.Http;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.ViewModels;

/// <summary>
/// Impostazioni dell'applicazione. Per ora: dati dell'utente, indirizzo del server e
/// cambio password. La password nuova vive solo nei PasswordBox e nella chiamata HTTP,
/// come nel login (§1.1).
/// </summary>
public partial class SettingsViewModel : ObservableObject
{
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private string? _successMessage;
    [ObservableProperty] private bool _isBusy;

    public string Username => App.Api.Client.CurrentUser?.Username ?? "—";
    public string DisplayName => App.Api.Client.CurrentUser?.DisplayName ?? "—";
    public string BaseCurrency => App.Api.Client.CurrentUser?.BaseCurrency ?? "—";
    public string ServerUrl => App.Api.Client.Settings.ApiBaseUrl;
    public string CertificatePath => App.Api.Client.Settings.ServerCertificatePath ?? "nessuno";

    // --- Dati di mercato ---------------------------------------------------

    public string[] Providers { get; } = ["alphavantage", "twelvedata", "none"];

    [ObservableProperty] private string _provider = "alphavantage";
    [ObservableProperty] private string _searchUrl = string.Empty;
    /// <summary>Vuoto = non toccare la chiave già salvata sul server.</summary>
    [ObservableProperty] private string _newApiKey = string.Empty;
    [ObservableProperty] private string _apiKeyStatus = "—";
    [ObservableProperty] private string _budgetStatus = "—";
    [ObservableProperty] private string? _marketDataMessage;

    private string _signupUrl = "https://www.alphavantage.co/support/#api-key";

    public async Task LoadMarketDataAsync()
    {
        try
        {
            var config = await App.Api.GetMarketDataSettingsAsync();
            Provider = config.Provider;
            SearchUrl = config.SearchUrl;
            _signupUrl = config.SignupUrl;
            ApiKeyStatus = config.ApiKeyConfigured
                ? $"configurata ({config.ApiKeyMasked})"
                : "non configurata — i prezzi vanno inseriti a mano";
            BudgetStatus = $"{config.UsedToday} richieste usate oggi " +
                           "(il piano gratuito Alpha Vantage ne concede 25)";
        }
        catch (Exception ex)
        {
            MarketDataMessage = "Impossibile leggere la configurazione: " + ex.Message;
        }
    }

    [RelayCommand]
    private async Task SaveMarketData()
    {
        MarketDataMessage = null;
        IsBusy = true;
        try
        {
            var config = await App.Api.SaveMarketDataSettingsAsync(
                Provider, string.IsNullOrWhiteSpace(NewApiKey) ? null : NewApiKey.Trim(), SearchUrl);
            NewApiKey = string.Empty;
            ApiKeyStatus = config.ApiKeyConfigured
                ? $"configurata ({config.ApiKeyMasked})"
                : "non configurata";
            MarketDataMessage = "Impostazioni salvate.";
        }
        catch (Services.ApiException ex)
        {
            MarketDataMessage = ex.Message;
        }
        catch (HttpRequestException ex)
        {
            MarketDataMessage = "Server non raggiungibile: " + ex.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    [RelayCommand]
    private void OpenSignup()
        => Process.Start(new ProcessStartInfo(_signupUrl) { UseShellExecute = true });

    // --- Azzeramento dei dati ---------------------------------------------

    [ObservableProperty] private string _resetConfirmation = string.Empty;
    [ObservableProperty] private string? _resetMessage;

    /// <summary>
    /// Cancella tutti i dati personali. Il server richiede password **e** la parola
    /// «AZZERA»: due barriere, perché l'operazione non ha un annulla.
    /// </summary>
    public async Task<bool> ResetDataAsync(string password)
    {
        ResetMessage = null;
        if (string.IsNullOrWhiteSpace(password))
        {
            ResetMessage = "Serve la password per confermare.";
            return false;
        }

        IsBusy = true;
        try
        {
            var result = await App.Api.ResetDataAsync(password, ResetConfirmation);
            ResetMessage = $"Eliminati {result.Total} elementi. I dati non sono recuperabili.";
            ResetConfirmation = string.Empty;
            return true;
        }
        catch (Services.ApiException ex)
        {
            ResetMessage = ex.Message;
            return false;
        }
        catch (HttpRequestException ex)
        {
            ResetMessage = "Server non raggiungibile: " + ex.Message;
            return false;
        }
        finally
        {
            IsBusy = false;
        }
    }

    /// <summary>
    /// Esito: <c>true</c> se la password è stata cambiata. In quel caso il chiamante deve
    /// riportare l'utente al login, perché il server ha revocato tutte le sessioni.
    /// </summary>
    public async Task<bool> ChangePasswordAsync(string current, string next, string confirmation)
    {
        ErrorMessage = null;
        SuccessMessage = null;

        if (string.IsNullOrWhiteSpace(current))
        {
            ErrorMessage = "Inserisci la password attuale.";
            return false;
        }

        // Stesso minimo imposto dal server (schemas.py, ChangePasswordRequest): meglio
        // dirlo qui subito che far tornare un 422 dopo il giro di rete.
        if (next.Length < 8)
        {
            ErrorMessage = "La nuova password deve essere di almeno 8 caratteri.";
            return false;
        }

        if (next != confirmation)
        {
            ErrorMessage = "Le due nuove password non coincidono.";
            return false;
        }

        if (next == current)
        {
            ErrorMessage = "La nuova password è identica a quella attuale.";
            return false;
        }

        IsBusy = true;
        try
        {
            await App.Api.ChangePasswordAsync(current, next);
            SuccessMessage = "Password cambiata. Tutte le sessioni sono state revocate: " +
                             "serve rifare il login.";
            return true;
        }
        catch (Services.ApiException ex)
        {
            ErrorMessage = ex.Message;
            return false;
        }
        catch (HttpRequestException ex)
        {
            ErrorMessage = "Server non raggiungibile: " + ex.Message;
            return false;
        }
        finally
        {
            IsBusy = false;
        }
    }
}
