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
