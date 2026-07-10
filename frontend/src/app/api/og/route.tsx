import { ImageResponse } from '@vercel/og';

export const runtime = 'edge';

export async function GET() {
  return new ImageResponse(
    (
      <div
        style={{
          fontSize: 48,
          background: 'linear-gradient(135deg, #1a1f3a 0%, #16213e 50%, #0f3460 100%)',
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontFamily: 'Arial, sans-serif',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Fondo decorativo con patrón */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background:
              'radial-gradient(circle at 20% 50%, rgba(255, 193, 7, 0.1) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(33, 150, 243, 0.1) 0%, transparent 50%)',
            pointerEvents: 'none',
          }}
        />

        {/* Contenido principal */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            textAlign: 'center',
          }}
        >
          {/* Emoji de balón */}
          <div style={{ fontSize: 100, marginBottom: 30 }}>⚽</div>

          {/* Título principal */}
          <div
            style={{
              fontSize: 72,
              fontWeight: 'bold',
              background: 'linear-gradient(90deg, #ffc107 0%, #2196f3 100%)',
              backgroundClip: 'text',
              color: 'transparent',
              marginBottom: 20,
              letterSpacing: '-2px',
            }}
          >
            Mundial Predictor
          </div>

          {/* Subtítulo */}
          <div
            style={{
              fontSize: 32,
              marginBottom: 40,
              color: '#ffc107',
              fontWeight: '600',
            }}
          >
            2026
          </div>

          {/* Descripción con tres columnas */}
          <div
            style={{
              display: 'flex',
              gap: 60,
              marginBottom: 30,
              justifyContent: 'center',
            }}
          >
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
              <div style={{ fontSize: 20, color: '#e0e0e0' }}>XGBoost</div>
            </div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>⭐</div>
              <div style={{ fontSize: 20, color: '#e0e0e0' }}>ELO</div>
            </div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>🎲</div>
              <div style={{ fontSize: 20, color: '#e0e0e0' }}>Monte Carlo</div>
            </div>
          </div>

          {/* Descripción final */}
          <div
            style={{
              fontSize: 24,
              color: '#b0bec5',
              marginTop: 20,
            }}
          >
            Predicciones en vivo • Análisis IA • Simulaciones
          </div>
        </div>

        {/* Footer decorativo */}
        <div
          style={{
            position: 'absolute',
            bottom: 30,
            left: 0,
            right: 0,
            display: 'flex',
            justifyContent: 'space-between',
            paddingLeft: 40,
            paddingRight: 40,
            fontSize: 18,
            color: '#607d8b',
          }}
        >
          <div>mundial-predictor.vercel.app</div>
          <div>FIFA 2026 • Jun 11 - Jul 19</div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
    },
  );
}
