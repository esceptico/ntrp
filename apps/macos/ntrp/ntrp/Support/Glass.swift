import AppKit
import SwiftUI

enum NtrpColors {
    static var window: Color { isDark ? Color(red: 0.063, green: 0.059, blue: 0.059) : Color(red: 0.925, green: 0.914, blue: 0.878) }
    static var canvas: Color { isDark ? darkPalette.canvas : Color(red: 0.980, green: 0.976, blue: 0.953) }
    static var glassTint: Color { isDark ? darkPalette.surface : Color(red: 0.955, green: 0.955, blue: 0.950) }
    static var sidebar: Color { glassTint }
    static var sidebarStroke: Color { isDark ? Color.white.opacity(0.12) : Color.black.opacity(0.11) }
    static var row: Color { isDark ? Color.white.opacity(0.055) : Color.black.opacity(0.045) }
    static var rowActive: Color { isDark ? Color.white.opacity(0.025) : Color.black.opacity(0.035) }
    static var rowActiveStroke: Color { isDark ? Color.white.opacity(0.06) : Color.black.opacity(0.07) }
    static var text: Color { isDark ? darkPalette.text : Color(red: 0.18, green: 0.18, blue: 0.17) }
    static var muted: Color { isDark ? darkPalette.muted : Color(red: 0.45, green: 0.44, blue: 0.41) }
    static var faint: Color { isDark ? darkPalette.faint : Color(red: 0.59, green: 0.57, blue: 0.53) }
    static var accent: Color { isDark ? darkPalette.accent : lightAccent }
    static var isDarkMode: Bool { isDark }
    static var isGlassMaterial: Bool {
        material == "glass"
    }
    static func surfaceFill(_ opacity: Double) -> Color {
        sidebar.opacity(isGlassMaterial ? min(opacity, 0.18) : opacity)
    }
    static var glassTintAlpha: Double {
        (UserDefaults.standard.object(forKey: "ntrp.glassTint") as? Double ?? 42) / 100
    }

    private static var theme: String {
        UserDefaults.standard.string(forKey: "ntrp.theme") ?? "system"
    }

    private static var material: String {
        switch UserDefaults.standard.string(forKey: "ntrp.material") ?? "linen" {
        case "glass":
            "glass"
        default:
            "linen"
        }
    }

    private static var palette: String {
        switch UserDefaults.standard.string(forKey: "ntrp.palette") ?? "graphite" {
        case "warm", "graphite", "raycast", "notion":
            UserDefaults.standard.string(forKey: "ntrp.palette") ?? "graphite"
        default:
            "graphite"
        }
    }

    private static var isDark: Bool {
        switch theme {
        case "light":
            false
        case "dark":
            true
        default:
            NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        }
    }

    private static var lightAccent: Color {
        switch palette {
        case "warm":
            Color(red: 0.72, green: 0.36, blue: 0.12)
        case "raycast":
            Color(red: 1.00, green: 0.39, blue: 0.39)
        case "notion":
            Color(red: 0.08, green: 0.08, blue: 0.08)
        default:
            Color(red: 0.06, green: 0.55, blue: 0.46)
        }
    }

    private static var darkPalette: PaletteColors {
        switch palette {
        case "warm":
            PaletteColors(
                canvas: Color(red: 0.110, green: 0.105, blue: 0.095),
                surface: Color(red: 0.130, green: 0.123, blue: 0.112),
                text: Color(red: 0.88, green: 0.86, blue: 0.82),
                muted: Color(red: 0.63, green: 0.61, blue: 0.56),
                faint: Color(red: 0.49, green: 0.47, blue: 0.42),
                accent: Color(red: 0.85, green: 0.44, blue: 0.17)
            )
        case "raycast":
            PaletteColors(
                canvas: Color(red: 0.070, green: 0.070, blue: 0.070),
                surface: Color(red: 0.100, green: 0.100, blue: 0.100),
                text: Color(red: 0.91, green: 0.90, blue: 0.89),
                muted: Color(red: 0.64, green: 0.63, blue: 0.62),
                faint: Color(red: 0.48, green: 0.47, blue: 0.46),
                accent: Color(red: 1.00, green: 0.39, blue: 0.39)
            )
        case "notion":
            PaletteColors(
                canvas: Color(red: 0.090, green: 0.090, blue: 0.086),
                surface: Color(red: 0.115, green: 0.115, blue: 0.110),
                text: Color(red: 0.92, green: 0.91, blue: 0.88),
                muted: Color(red: 0.64, green: 0.63, blue: 0.59),
                faint: Color(red: 0.49, green: 0.48, blue: 0.44),
                accent: Color.white
            )
        default:
            PaletteColors(
                canvas: Color(red: 0.047, green: 0.050, blue: 0.052),
                surface: Color(red: 0.078, green: 0.086, blue: 0.090),
                text: Color(red: 0.88, green: 0.89, blue: 0.88),
                muted: Color(red: 0.63, green: 0.64, blue: 0.62),
                faint: Color(red: 0.48, green: 0.49, blue: 0.47),
                accent: Color(red: 0.33, green: 0.84, blue: 0.75)
            )
        }
    }
}

private struct PaletteColors {
    let canvas: Color
    let surface: Color
    let text: Color
    let muted: Color
    let faint: Color
    let accent: Color
}

struct NtrpModalScrim: View {
    var body: some View {
        Rectangle()
            .fill(NtrpColors.isDarkMode ? Color.black.opacity(0.32) : Color(red: 0.08, green: 0.095, blue: 0.11).opacity(0.08))
            .background(.ultraThinMaterial)
    }
}

struct NtrpScrollTopMask: View {
    let scrolled: Bool

    var body: some View {
        if scrolled {
            LinearGradient(
                stops: [
                    .init(color: .clear, location: 0.0),
                    .init(color: .black.opacity(0.08), location: 0.03),
                    .init(color: .black.opacity(0.40), location: 0.08),
                    .init(color: .black, location: 0.17)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        } else {
            Rectangle()
        }
    }
}

struct NtrpThemeBridge: ViewModifier {
    @AppStorage("ntrp.theme") private var theme = "system"
    @AppStorage("ntrp.palette") private var palette = "graphite"
    @AppStorage("ntrp.material") private var material = "linen"
    @AppStorage("ntrp.glassTint") private var glassTint = 42.0
    @AppStorage("ntrp.glassBlur") private var glassBlur = 12.0
    @AppStorage("ntrp.glassSaturate") private var glassSaturate = 140.0
    @AppStorage("ntrp.glassRim") private var glassRim = 42.0

    func body(content: Content) -> some View {
        content
            .preferredColorScheme(colorScheme)
            .id("theme-\(theme)-\(normalizedPalette)-\(normalizedMaterial)-\(glassTint)-\(glassBlur)-\(glassSaturate)-\(glassRim)")
    }

    private var colorScheme: ColorScheme? {
        switch theme {
        case "light": .light
        case "dark": .dark
        default: nil
        }
    }

    private var normalizedPalette: String {
        switch palette {
        case "warm", "graphite", "raycast", "notion": palette
        default: "graphite"
        }
    }

    private var normalizedMaterial: String {
        material == "glass" ? "glass" : "linen"
    }
}

extension View {
    @ViewBuilder
    func ntrpGlass(cornerRadius: CGFloat, interactive: Bool = false) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        if #available(macOS 26.0, *), NtrpColors.isGlassMaterial {
            if interactive {
                self.glassEffect(.regular.tint(NtrpColors.sidebar.opacity(NtrpColors.glassTintAlpha)).interactive(), in: shape)
            } else {
                self.glassEffect(.regular.tint(NtrpColors.sidebar.opacity(NtrpColors.glassTintAlpha)), in: shape)
            }
        } else if NtrpColors.isGlassMaterial {
            self.background(.ultraThinMaterial, in: shape)
        } else {
            self
        }
    }
}

struct NtrpSpinner: View {
    var size: CGFloat = 12
    var lineWidth: CGFloat = 1.5
    var color: Color = NtrpColors.faint
    var duration: Double = 0.9

    var body: some View {
        TimelineView(.animation) { context in
            let progress = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: duration) / duration
            Circle()
                .trim(from: 0.12, to: 0.82)
                .stroke(color, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
                .rotationEffect(.degrees(progress * 360))
                .frame(width: size, height: size)
                .allowsHitTesting(false)
        }
    }
}
