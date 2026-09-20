using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

namespace Centesimo.Desktop.Converters;

public sealed class InverseBoolConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is bool b ? !b : true;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => value is bool b ? !b : false;
}

/// <summary>Verde per le entrate, rosso per le uscite: colore usato solo per il segno.</summary>
public sealed class AmountToBrushConverter : IValueConverter
{
    private static readonly Brush Positive = new SolidColorBrush(Color.FromRgb(0x3F, 0xBF, 0x7F));
    private static readonly Brush Negative = new SolidColorBrush(Color.FromRgb(0xE5, 0x55, 0x6E));
    private static readonly Brush Neutral = new SolidColorBrush(Color.FromRgb(0xE9, 0xEC, 0xF2));

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value switch
        {
            decimal d when d > 0 => Positive,
            decimal d when d < 0 => Negative,
            _ => Neutral
        };

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Rende visibile un elemento solo se la stringa non è vuota.</summary>
public sealed class StringToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => string.IsNullOrWhiteSpace(value as string) ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

public sealed class BoolToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is true ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => value is Visibility.Visible;
}

/// <summary>
/// Formattazione del denaro, unica in tutta l'applicazione: due decimali, virgola
/// decimale e punto per le migliaia (cultura it-IT), e la <b>sigla</b> della valuta al
/// posto del simbolo — "1.234,56 EUR", non "1.234,56 €".
///
/// La sigla arriva dal <c>ConverterParameter</c> quando la riga ha una valuta propria
/// (il portafoglio tiene le posizioni in valuta nativa, §2.8); in mancanza si usa EUR.
/// Un valore nullo diventa "—": una cella vuota non distingue "non lo so" da "zero".
/// </summary>
public sealed class MoneyConverter : IValueConverter
{
    public const string Missing = "—";

    private static readonly CultureInfo Italian = CultureInfo.GetCultureInfo("it-IT");

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var amount = value switch
        {
            decimal d => d,
            double d => (decimal)d,
            int i => i,
            _ => (decimal?)null
        };

        if (amount is null)
        {
            return Missing;
        }

        var code = parameter as string;
        var text = amount.Value.ToString("N2", Italian);
        return string.IsNullOrWhiteSpace(code) ? $"{text} EUR" : $"{text} {code}";
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Come <see cref="MoneyConverter"/> ma senza sigla: per le quantità di titoli.</summary>
public sealed class QuantityConverter : IValueConverter
{
    private static readonly CultureInfo Italian = CultureInfo.GetCultureInfo("it-IT");

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        if (value is not decimal quantity)
        {
            return MoneyConverter.Missing;
        }

        // Le quantità sono NUMERIC(24,8): gli zeri finali non dicono nulla e allungano
        // la colonna, quindi si tagliano.
        var trimmed = quantity.ToString("0.########", Italian);
        return trimmed.Length == 0 ? "0" : trimmed;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Percentuale con segno esplicito: "+12,34 %".</summary>
public sealed class PercentConverter : IValueConverter
{
    private static readonly CultureInfo Italian = CultureInfo.GetCultureInfo("it-IT");

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var percent = value switch
        {
            decimal d => (double)d,
            double d => d,
            _ => (double?)null
        };

        if (percent is null)
        {
            return MoneyConverter.Missing;
        }

        var sign = percent.Value > 0 ? "+" : string.Empty;
        return $"{sign}{percent.Value.ToString("N2", Italian)} %";
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Colora la barra del budget di rosso quando il limite è superato (§2.5).</summary>
public sealed class OverBudgetToBrushConverter : IValueConverter
{
    private static readonly Brush Over = new SolidColorBrush(Color.FromRgb(0xE5, 0x55, 0x6E));
    private static readonly Brush Ok = new SolidColorBrush(Color.FromRgb(0x4C, 0x8D, 0xFF));

    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is true ? Over : Ok;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
