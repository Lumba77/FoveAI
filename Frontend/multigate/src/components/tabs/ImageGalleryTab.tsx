import React, { useState } from 'react';

const IMAGES = [
  "016e8fb51d2023d61f7bc28eeff77a54.png",
  "1088c135-4350-42ee-a1b9-1d68bc764f49.png",
  "1750fa1b-44e9-47a3-93a6-24c4da767606.png",
  "3e68c10d-9d66-4f05-b8bc-79f689091e40.png",
  "45b206c8-de7b-4e88-aac2-c6ad4ce9f801.png",
  "47dc1edd-d6d6-4471-b0a3-1cd4dc8f5c9c.png",
  "4aae3876-0c11-468e-b248-fd6d14dea163.png",
  "4b7a2583-16af-4789-9501-e7811c9daa56 (Medium) (Small).png",
  "4f824fe4-fa9a-4f05-91fc-e9d97d3069a6.png",
  "5cf0f89f-12fc-4d74-9b29-2219e254bb56.png",
  "628fc379-e46a-4312-84c9-57d5dd003dea.png",
  "6b59af80-b6ca-4e6f-a881-eb5a38319c72.jpg",
  "907ffd6e-350f-408c-82f6-3f23c0b2bc10.png",
  "A crazy representation of a wild widely retarded c (1).jpg",
  "c53e9632-1f2a-40df-9081-d8b5ce62b19d.png",
  "ceb267a5-d2d7-4267-b532-96462f18549d.png",
  "e6bf5b0d-b070-4783-a099-429c19fb2b4a (1).png",
  "f13003df-2c5e-4cf8-ae1b-879526606cb2.png",
  "PXL_20241129_105217978.RAW-01.COVER.jpg",
  "QVZleVgzOWZVM0k5VGlWbg.jpeg",
  "malninga.jpg"
];

export const ImageGalleryTab: React.FC = () => {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto', background: 'transparent' }}>
      <h1 style={{ color: 'var(--accent-cyan)', marginBottom: '20px', textShadow: '0 0 10px var(--accent-cyan)' }}>Lumba Image Gallery</h1>
      
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '20px'
      }}>
        {IMAGES.map((img, i) => (
          <div 
            key={i} 
            onClick={() => setSelectedImage(img)}
            style={{
              cursor: 'pointer',
              borderRadius: '8px',
              overflow: 'hidden',
              background: 'rgba(0,0,0,0.4)',
              border: '1px solid rgba(255,255,255,0.1)',
              aspectRatio: '1',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'transform 0.2s, box-shadow 0.2s'
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'scale(1.05)';
              e.currentTarget.style.boxShadow = '0 0 15px var(--accent-cyan)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <img 
              src={`/Lumba bilder/${img}`} 
              alt={img} 
              style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
              loading="lazy"
            />
          </div>
        ))}
      </div>

      {selectedImage && (
        <div 
          onClick={() => setSelectedImage(null)}
          style={{
            position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
            background: 'rgba(0,0,0,0.85)', zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'zoom-out'
          }}
        >
          <img 
            src={`/Lumba bilder/${selectedImage}`} 
            style={{ maxWidth: '90%', maxHeight: '90%', borderRadius: '12px', boxShadow: '0 0 30px #000' }} 
            alt="Enlarged" 
          />
        </div>
      )}
    </div>
  );
};
