using System.Windows;
using System.Windows.Controls;

namespace Centesimo.Desktop.Controls;

/// <summary>
/// Testo segnaposto per i campi di input: <c>ctrl:Hint.Text="Nome del conto"</c>.
///
/// Convenzione unica dell'applicazione: la descrizione del campo sta <b>dentro</b> il
/// riquadro, breve e con l'iniziale maiuscola — niente etichetta separata sopra. Un
/// <c>ToolTip</c> non basta: si vede solo passandoci sopra, e davanti a una colonna di
/// riquadri identici non dice nulla.
///
/// <see cref="TextBox"/> e <see cref="DatePicker"/> se la cavano con un trigger sul
/// template (<c>Text</c> e <c>SelectedDate</c> sono proprietà di dipendenza).
/// <see cref="PasswordBox"/> no: <c>Password</c> non è una proprietà di dipendenza, quindi
/// nessun trigger può osservarla. Per quello c'è <see cref="IsEmptyProperty"/>, tenuta
/// aggiornata qui sotto agganciandosi a <c>PasswordChanged</c>.
/// </summary>
public static class Hint
{
    public static readonly DependencyProperty TextProperty =
        DependencyProperty.RegisterAttached(
            "Text", typeof(string), typeof(Hint),
            new PropertyMetadata(string.Empty, OnTextChanged));

    public static void SetText(DependencyObject element, string value)
        => element.SetValue(TextProperty, value);

    public static string GetText(DependencyObject element)
        => (string)element.GetValue(TextProperty);

    /// <summary>
    /// Vero quando il campo è vuoto. Serve solo al <see cref="PasswordBox"/>, dove non
    /// esiste una proprietà di dipendenza su cui far scattare un trigger.
    /// </summary>
    public static readonly DependencyProperty IsEmptyProperty =
        DependencyProperty.RegisterAttached(
            "IsEmpty", typeof(bool), typeof(Hint), new PropertyMetadata(true));

    public static void SetIsEmpty(DependencyObject element, bool value)
        => element.SetValue(IsEmptyProperty, value);

    public static bool GetIsEmpty(DependencyObject element)
        => (bool)element.GetValue(IsEmptyProperty);

    private static void OnTextChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not PasswordBox box)
        {
            return;
        }

        // Idempotente: assegnare di nuovo Hint.Text non deve moltiplicare le iscrizioni.
        box.PasswordChanged -= OnPasswordChanged;
        box.PasswordChanged += OnPasswordChanged;
        SetIsEmpty(box, box.Password.Length == 0);
    }

    private static void OnPasswordChanged(object sender, RoutedEventArgs e)
    {
        if (sender is PasswordBox box)
        {
            SetIsEmpty(box, box.Password.Length == 0);
        }
    }
}
