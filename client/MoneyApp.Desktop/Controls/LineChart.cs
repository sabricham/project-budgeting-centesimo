using System.Collections;
using System.Collections.Specialized;
using System.Globalization;
using System.Windows;
using System.Windows.Media;
using MoneyApp.Desktop.Models;

namespace MoneyApp.Desktop.Controls;

/// <summary>
/// Grafico a linea/area disegnato a mano su WPF.
///
/// Perché non una libreria di charting: per due serie semplici (saldo e patrimonio) una
/// dipendenza esterna aggiungerebbe peso e vincoli di licenza senza dare nulla che qui
/// serva davvero. Il disegno è ~100 righe e non ha dipendenze.
/// </summary>
public sealed class LineChart : FrameworkElement
{
    public static readonly DependencyProperty ItemsSourceProperty = DependencyProperty.Register(
        nameof(ItemsSource), typeof(IEnumerable), typeof(LineChart),
        new FrameworkPropertyMetadata(null, FrameworkPropertyMetadataOptions.AffectsRender, OnItemsSourceChanged));

    public static readonly DependencyProperty StrokeProperty = DependencyProperty.Register(
        nameof(Stroke), typeof(Brush), typeof(LineChart),
        new FrameworkPropertyMetadata(Brushes.DodgerBlue, FrameworkPropertyMetadataOptions.AffectsRender));

    public IEnumerable? ItemsSource
    {
        get => (IEnumerable?)GetValue(ItemsSourceProperty);
        set => SetValue(ItemsSourceProperty, value);
    }

    public Brush Stroke
    {
        get => (Brush)GetValue(StrokeProperty);
        set => SetValue(StrokeProperty, value);
    }

    private static void OnItemsSourceChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        var chart = (LineChart)d;
        if (e.OldValue is INotifyCollectionChanged oldCollection)
        {
            oldCollection.CollectionChanged -= chart.OnCollectionChanged;
        }
        if (e.NewValue is INotifyCollectionChanged newCollection)
        {
            newCollection.CollectionChanged += chart.OnCollectionChanged;
        }
    }

    private void OnCollectionChanged(object? sender, NotifyCollectionChangedEventArgs e) => InvalidateVisual();

    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc);

        var points = ItemsSource?.Cast<TimeseriesPoint>().ToList() ?? [];
        var width = ActualWidth;
        var height = ActualHeight;
        if (width <= 1 || height <= 1)
        {
            return;
        }

        var axisPen = new Pen(new SolidColorBrush(Color.FromRgb(0x33, 0x39, 0x45)), 1);
        axisPen.Freeze();

        if (points.Count < 2)
        {
            var typeface = new Typeface("Segoe UI");
            var text = new FormattedText("Dati insufficienti per il grafico",
                CultureInfo.CurrentCulture, FlowDirection.LeftToRight, typeface, 12,
                new SolidColorBrush(Color.FromRgb(0x9A, 0xA3, 0xB2)), 96);
            dc.DrawText(text, new Point((width - text.Width) / 2, (height - text.Height) / 2));
            return;
        }

        const double padding = 8;
        var min = points.Min(p => p.Value);
        var max = points.Max(p => p.Value);
        if (max == min)
        {
            // serie piatta: si allarga la scala per non disegnare una linea sul bordo
            max += 1;
            min -= 1;
        }

        double X(int index) => padding + index * (width - 2 * padding) / (points.Count - 1);
        double Y(decimal value) => height - padding -
                                   (double)((value - min) / (max - min)) * (height - 2 * padding);

        // linea dello zero, quando la serie attraversa lo zero (utile sul patrimonio netto)
        if (min < 0 && max > 0)
        {
            var zero = Y(0);
            dc.DrawLine(axisPen, new Point(padding, zero), new Point(width - padding, zero));
        }

        var geometry = new StreamGeometry();
        using (var ctx = geometry.Open())
        {
            ctx.BeginFigure(new Point(X(0), Y(points[0].Value)), false, false);
            for (var i = 1; i < points.Count; i++)
            {
                ctx.LineTo(new Point(X(i), Y(points[i].Value)), true, false);
            }
        }
        geometry.Freeze();

        var area = new StreamGeometry();
        using (var ctx = area.Open())
        {
            ctx.BeginFigure(new Point(X(0), height - padding), true, true);
            for (var i = 0; i < points.Count; i++)
            {
                ctx.LineTo(new Point(X(i), Y(points[i].Value)), true, false);
            }
            ctx.LineTo(new Point(X(points.Count - 1), height - padding), true, false);
        }
        area.Freeze();

        var stroke = Stroke as SolidColorBrush ?? Brushes.DodgerBlue;
        var fill = new SolidColorBrush(Color.FromArgb(48, stroke.Color.R, stroke.Color.G, stroke.Color.B));
        fill.Freeze();

        dc.DrawGeometry(fill, null, area);

        var pen = new Pen(stroke, 2) { LineJoin = PenLineJoin.Round };
        pen.Freeze();
        dc.DrawGeometry(null, pen, geometry);
    }
}
