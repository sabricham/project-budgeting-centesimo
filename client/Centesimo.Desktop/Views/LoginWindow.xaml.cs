using System.Windows;
using System.Windows.Input;
using Centesimo.Desktop.ViewModels;

namespace Centesimo.Desktop.Views;

public partial class LoginWindow : Window
{
    private readonly LoginViewModel _viewModel = new();

    public LoginWindow()
    {
        InitializeComponent();
        DataContext = _viewModel;
        Loaded += (_, _) => UsernameBox.Focus();
    }

    private async void Login_Click(object sender, RoutedEventArgs e) => await TryLoginAsync();

    private async void PasswordBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            await TryLoginAsync();
        }
    }

    private async Task TryLoginAsync()
    {
        // La password non lascia mai il PasswordBox se non per la chiamata di login (§1.1).
        if (await _viewModel.LoginAsync(PasswordBox.Password))
        {
            DialogResult = true;
            Close();
        }
    }
}
