document.addEventListener('DOMContentLoaded', () => {

    // Navbar scroll class
    const navbar = document.getElementById('navbar');
    const onScroll = () => {
        navbar.classList.toggle('scrolled', window.scrollY > 40);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    // Hamburger
    const hamburger = document.getElementById('hamburger');
    const navLinks = document.querySelector('.nav-links');
    if (hamburger && navLinks) {
        hamburger.addEventListener('click', () => {
            const open = navLinks.style.display === 'flex';
            Object.assign(navLinks.style, {
                display: open ? '' : 'flex',
                flexDirection: 'column',
                position: 'absolute',
                top: '100%', left: '0', right: '0',
                background: 'rgba(245,242,232,0.98)',
                padding: '1.5rem 5%',
                gap: '1.2rem',
                boxShadow: '0 8px 32px rgba(26,34,24,0.1)',
                zIndex: '200'
            });
        });
    }

    // Smooth scroll for nav links
    document.querySelectorAll('a[href^="#"]').forEach(a => {
        a.addEventListener('click', e => {
            const target = document.querySelector(a.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // Dynamic Footer Copyright Year
    const copyrightYear = document.getElementById('copyrightYear');
    if (copyrightYear) {
        copyrightYear.textContent = new Date().getFullYear();
    }

    // Footer Newsletter Real-time Interactive Handler
    const newsletterForm = document.getElementById('footerNewsletterForm');
    const newsletterSuccess = document.getElementById('newsletterSuccess');
    if (newsletterForm && newsletterSuccess) {
        newsletterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            newsletterSuccess.style.display = 'block';
            newsletterForm.reset();
            setTimeout(() => {
                newsletterSuccess.style.display = 'none';
            }, 4000);
        });
    }

});
