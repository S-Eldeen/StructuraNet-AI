
import './homepage.css';
import { Link } from "react-router-dom";
import { TypeAnimation } from 'react-type-animation';
import { useState, useRef } from "react";

const Homepage = () => {
    const [showContent, setShowContent] = useState(false);
    const audioRef = useRef(null);

    return (
        <div className="homepage">
            <img src="/orbital.png" alt="Orbital Background" className='orbital' />
            {/* Background Glow */}
            <div className="bg-glow"></div>

            {/* INTRO */}
            <div className={`intro ${showContent ? "hide" : ""}`}>

                <div className="bot-wrapper">

                    <img
                        src="/robot.gif"
                        alt="AI Robot"
                        className="intro-bot"
                    />

                    {/* Chat Bubble */}
                    <div className="chat-bubble">
                        <TypeAnimation
                            sequence={[
                                () => {
                                    audioRef.current?.play().catch(() => { });
                                },

                                "Hello 👋",
                                900,

                                "I am Structa 🤖",
                                1200,

                                "Your Network AI Assistant",
                                1500,

                                "Let’s build something amazing 🚀",
                                1500,

                                () => {
                                    audioRef.current?.pause();
                                    setShowContent(true);
                                }
                            ]}
                            speed={50}
                            cursor={true}
                        />
                    </div>

                </div>
            </div>

            {/* typing sound (اختياري) */}
            {/* <audio ref={audioRef} src="/typing.mp3" loop /> */}

            {/* MAIN CONTENT */}
            <div className={`main ${showContent ? "show" : ""}`}>

                <h1>Structranet AI</h1>

                <h2>Design. Simulate. Deploy.</h2>

                <div className="description">
                    <h5>Design complex network topologies with ease.</h5>
                    <h5>Validate and deploy them automatically.</h5>
                </div>

                <Link to="/dashboard" className="get-started-btn">
                    Get Started
                </Link>

            </div>

        </div>
    );
};

export default Homepage;
