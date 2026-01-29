/**
 * Icons Component - Using React Icons
 * Feather icons for a clean, professional look
 */

import {
    // General
    FiUpload, FiSun, FiMoon, FiTrash2, FiRefreshCw, FiPlay, FiPause, FiSquare,
    FiVolume2, FiVolumeX, FiLoader, FiAlertCircle, FiCheckCircle, FiClock,
    FiChevronDown, FiChevronUp, FiSend, FiX, FiSettings, FiInfo,

    // Content
    FiFileText, FiMessageCircle, FiBook, FiBookOpen, FiList, FiMic,
    FiVideo, FiMusic, FiHash, FiHeart, FiGlobe, FiZap,

    // Navigation
    FiHome, FiMenu, FiMoreVertical, FiHelpCircle
} from 'react-icons/fi';

import {
    // Heroicons for some extras
    HiOutlineSparkles, HiOutlineLightBulb, HiOutlineTranslate,
    HiOutlineDocumentText, HiOutlineAcademicCap
} from 'react-icons/hi';

import {
    // Bootstrap icons
    BiPlay, BiStop
} from 'react-icons/bi';

// Exported icons with consistent naming
export const Icons = {
    // App - Using Heart for spiritual feel
    Logo: (props) => <FiHeart {...props} />,
    Spiritual: (props) => <FiHeart {...props} />,

    // Theme
    Sun: (props) => <FiSun {...props} />,
    Moon: (props) => <FiMoon {...props} />,

    // Actions
    Upload: (props) => <FiUpload {...props} />,
    Send: (props) => <FiSend {...props} />,
    Delete: (props) => <FiTrash2 {...props} />,
    Refresh: (props) => <FiRefreshCw {...props} />,
    Close: (props) => <FiX {...props} />,
    Settings: (props) => <FiSettings {...props} />,
    Info: (props) => <FiInfo {...props} />,
    MoreVertical: (props) => <FiMoreVertical {...props} />,

    // Media
    Play: (props) => <FiPlay {...props} />,
    Pause: (props) => <FiPause {...props} />,
    Stop: (props) => <FiSquare {...props} />,
    VolumeOn: (props) => <FiVolume2 {...props} />,
    VolumeOff: (props) => <FiVolumeX {...props} />,
    Mic: (props) => <FiMic {...props} />,
    Video: (props) => <FiVideo {...props} />,
    Music: (props) => <FiMusic {...props} />,

    // Status
    Loading: (props) => <FiLoader {...props} />,
    Error: (props) => <FiAlertCircle {...props} />,
    Success: (props) => <FiCheckCircle {...props} />,
    Clock: (props) => <FiClock {...props} />,

    // Content
    Transcript: (props) => <FiFileText {...props} />,
    Summary: (props) => <HiOutlineDocumentText {...props} />,
    Explanation: (props) => <HiOutlineLightBulb {...props} />,
    Chat: (props) => <FiMessageCircle {...props} />,
    Question: (props) => <FiHelpCircle {...props} />,
    Book: (props) => <FiBook {...props} />,
    BookOpen: (props) => <FiBookOpen {...props} />,
    List: (props) => <FiList {...props} />,
    Sessions: (props) => <FiBook {...props} />,

    // Features
    Sparkles: (props) => <HiOutlineSparkles {...props} />,
    Translate: (props) => <HiOutlineTranslate {...props} />,
    Speak: (props) => <FiVolume2 {...props} />,
    AI: (props) => <FiZap {...props} />,
    Globe: (props) => <FiGlobe {...props} />,

    // Chevrons
    ChevronDown: (props) => <FiChevronDown {...props} />,
    ChevronUp: (props) => <FiChevronUp {...props} />,

    // Processing steps
    Processing: (props) => <FiLoader {...props} />,
    Done: (props) => <FiCheckCircle {...props} />,
    Pending: (props) => <FiClock {...props} />,
};

export default Icons;
