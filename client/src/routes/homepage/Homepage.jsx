import './homepage.css';
import { Link } from "react-router-dom";
import { TypeAnimation } from 'react-type-animation';
import { useState } from "react";

const Homepage = () => {
    const [typingStatus, setTypingStatus] = useState("human1");

    return (
        <div className='homepage'>
            <img src="/orbital.png" alt="Orbital Background" className='orbital' />
            
            <div className="left">
                <h1>StructraNet AI</h1>
                <h2>Design. Simulate. Deploy.</h2>
                <div className="description">
                    <h5>Design complex network topologies with ease.</h5>
                    <h5>Validate and deploy them automatically with StructraNet.</h5>
                </div>
                <Link to="/dashboard" className="get-started-btn">✨ Get Started</Link>
            </div>
            
            <div className="right">
                <div className="imgContainer">
                    <div className="bgContainer">
                        <div className="bg"></div>
                    </div>
                    <img src="/bot.png" alt="Bot" className="bot" />
                    <div className="chat">
                        <img 
                            src={typingStatus === "human1" ? "/human1.jpeg" :
                                typingStatus === "human2" ? "/human2.jpeg" : "/logo.png"} 
                            alt="avatar"
                        />
                        <TypeAnimation
                            sequence={[
                                '🤖 Structra: We produce food for Mice',
                                2000,
                                () => { setTypingStatus("Structra") },
                                '👨‍💻 human: We produce food for Hamsters',
                                2000,
                                () => { setTypingStatus("human2") },
                                '🤖 Structra: We produce food for Guinea Pigs',
                                2000,
                                () => { setTypingStatus("Structra") },
                                '👩‍💻 human: We produce food for Chinchillas',
                                2000,
                                () => { setTypingStatus("human1") },
                            ]}
                            repeat={Infinity}
                            wrapper="span"
                            speed={50}
                            deletionSpeed={50}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Homepage;