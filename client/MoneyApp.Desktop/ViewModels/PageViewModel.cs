using System.Net.Http;
using CommunityToolkit.Mvvm.ComponentModel;
using MoneyApp.Desktop.Services;

namespace MoneyApp.Desktop.ViewModels;

/// <summary>
/// Base delle pagine: stato di caricamento e gestione uniforme degli errori dell'API.
///
/// Nota sul contratto (§1.3): la validazione che conta è quella del server. Qui si
/// mostra solo il messaggio che il server restituisce, senza reimplementare le regole.
/// </summary>
public abstract partial class PageViewModel : ObservableObject
{
    [ObservableProperty]
    private bool _isBusy;

    [ObservableProperty]
    private string? _errorMessage;

    [ObservableProperty]
    private string? _statusMessage;

    public abstract string Title { get; }

    public virtual string Glyph => "•";

    protected static MoneyApi Api => App.Api;

    public virtual Task LoadAsync() => Task.CompletedTask;

    /// <summary>Esegue un'operazione mostrando errori e stato di attesa.</summary>
    protected async Task RunAsync(Func<Task> action, string? successMessage = null)
    {
        if (IsBusy)
        {
            return;
        }

        IsBusy = true;
        ErrorMessage = null;
        try
        {
            await action();
            StatusMessage = successMessage;
        }
        catch (ApiException ex)
        {
            ErrorMessage = ex.Message;
            StatusMessage = null;
        }
        catch (HttpRequestException ex)
        {
            ErrorMessage = $"Server non raggiungibile ({ex.Message}). Controlla che i container siano avviati.";
            StatusMessage = null;
        }
        finally
        {
            IsBusy = false;
        }
    }
}
