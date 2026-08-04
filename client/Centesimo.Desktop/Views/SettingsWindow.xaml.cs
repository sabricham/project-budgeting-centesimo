using System.Windows;
using System.Windows.Input;
using Centesimo.Desktop.ViewModels;

namespace Centesimo.Desktop.Views;

public partial class SettingsWindow : Window
{
    private readonly SettingsViewModel _viewModel = new();

    public SettingsWindow()
    {
        InitializeComponent();
        DataContext = _viewModel;
        Loaded += async (_, _) => await _viewModel.LoadMarketDataAsync();
    }

    /// <summary>
    /// La chiave non passa da una proprietà del ViewModel legata all'interfaccia: resta
    /// nel PasswordBox e viene letta solo al salvataggio, come le password (§1.1).
    /// </summary>
    private void ApiKeyBox_PasswordChanged(object sender, RoutedEventArgs e)
        => _viewModel.NewApiKey = ApiKeyBox.Password;

    private async void Reset_Click(object sender, RoutedEventArgs e)
    {
        var answer = MessageBox.Show(this,
            "Stai per cancellare definitivamente tutti i tuoi dati: conti, movimenti, " +
            "categorie, budget, obiettivi, ricorrenze e portafoglio.\n\n" +
            "L'operazione non è annullabile. Vuoi procedere?",
            "Centesimo — azzeramento", MessageBoxButton.YesNo, MessageBoxImage.Warning,
            MessageBoxResult.No);

        if (answer != MessageBoxResult.Yes)
        {
            return;
        }

        if (await _viewModel.ResetDataAsync(ResetPasswordBox.Password))
        {
            ResetPasswordBox.Clear();
            MessageBox.Show(this,
                "Dati azzerati. L'applicazione si chiude: al prossimo avvio ripartirai da vuoto.",
                "Centesimo", MessageBoxButton.OK, MessageBoxImage.Information);
            Application.Current.Shutdown();
        }
    }

    /// <summary>
    /// <c>true</c> se la password è stata cambiata: il chiamante deve riportare
    /// l'utente al login, perché il server ha revocato ogni sessione.
    /// </summary>
    public bool PasswordChanged { get; private set; }

    private async void ChangePassword_Click(object sender, RoutedEventArgs e) => await TryChangeAsync();

    private async void ConfirmPasswordBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            await TryChangeAsync();
        }
    }

    private async Task TryChangeAsync()
    {
        // Le password non lasciano i PasswordBox se non per la chiamata (§1.1).
        var changed = await _viewModel.ChangePasswordAsync(
            CurrentPasswordBox.Password, NewPasswordBox.Password, ConfirmPasswordBox.Password);

        if (!changed)
        {
            return;
        }

        PasswordChanged = true;
        CurrentPasswordBox.Clear();
        NewPasswordBox.Clear();
        ConfirmPasswordBox.Clear();

        MessageBox.Show(this,
            "Password cambiata.\n\nTutte le sessioni sono state revocate: l'applicazione " +
            "si chiude e al prossimo avvio serve rifare il login.",
            "Centesimo", MessageBoxButton.OK, MessageBoxImage.Information);

        DialogResult = true;
        Close();
    }

    private void Close_Click(object sender, RoutedEventArgs e) => Close();
}
